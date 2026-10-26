"""Mouse simulado: nenhum teste abre X11 ou altera o cursor real."""

from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from hand_control.gestures import GestureEvent, to_event

from hand_control.mouse_control import (
    AsyncMouseBackend, CoordinateMapper, HandTracking, MouseController,
    FistClickDetector, X11MouseBackend, extract_tracking,
)


def tracking(point=(0.5, 0.5)):
    return HandTracking(point)


class FakeMouse:
    def __init__(self):
        self.size = (1001, 801)
        self.error = self.position = None
        self.commands = []
        self.active = False
        self.accept = True

    def activate(self):
        self.active = True

    def poll(self):
        pass

    def suspend(self):
        self.active = False

    def submit(self, x, y, click):
        if not self.accept:
            return False
        self.active = True
        self.position = (x, y)
        self.commands.append((x, y, click))
        return True

    def close(self):
        self.active = False

    @property
    def clicks(self):
        return sum(command[2] for command in self.commands)


class GeometryTests(unittest.TestCase):
    def test_mapping_margin_and_screen_bounds(self):
        mapper = CoordinateMapper((1001, 801), margin=0.1, smoothing=1)
        self.assertEqual(mapper.map((0.1, 0.1)), (0, 0))
        self.assertEqual(mapper.map((0.9, 0.9)), (1000, 800))
        self.assertEqual(mapper.map((0.5, 0.5)), (500, 400))
        self.assertEqual(mapper.map((-1, 2)), (0, 800))

    def test_exponential_smoothing_and_reset(self):
        mapper = CoordinateMapper((1001, 801), margin=0, smoothing=0.25)
        self.assertEqual(mapper.map((0, 0)), (0, 0))
        self.assertEqual(mapper.map((1, 1)), (250, 200))
        self.assertEqual(mapper.map((1, 1)), (438, 350))
        mapper.reset()
        self.assertEqual(mapper.map((1, 1)), (1000, 800))

    def test_already_mirrored_input_is_not_flipped_twice(self):
        mirrored = CoordinateMapper((1001, 801), margin=0, smoothing=1)
        raw = CoordinateMapper((1001, 801), margin=0, smoothing=1, mirrored_input=False)
        self.assertEqual(mirrored.map((0.2, 0.3)), (200, 240))
        self.assertEqual(raw.map((0.8, 0.3)), (200, 240))

    def test_first_hand_index_is_reused_at_different_scales(self):
        for scale in (0.5, 1):
            hand = [SimpleNamespace(x=0.5, y=0.5) for _ in range(21)]
            hand[0] = SimpleNamespace(x=0.5, y=0.5 + 0.2 * scale)
            hand[4] = SimpleNamespace(x=0.5 + 0.04 * scale, y=0.5)
            observed = extract_tracking(SimpleNamespace(hand_landmarks=[hand]), 4 / 3)
            self.assertEqual(observed.index, (0.5, 0.5))

    def test_missing_incomplete_nonfinite_or_degenerate_tracking_is_rejected(self):
        hand = [SimpleNamespace(x=0.5, y=0.5) for _ in range(21)]
        for hands in ([], [hand[:8]], [hand]):
            self.assertIsNone(extract_tracking(SimpleNamespace(hand_landmarks=hands), 4 / 3))
        hand[0] = SimpleNamespace(x=0.5, y=0.8)
        for bad in (float('nan'), float('inf'), -0.1, 1.1):
            hand[8] = SimpleNamespace(x=bad, y=0.5)
            self.assertIsNone(extract_tracking(SimpleNamespace(hand_landmarks=[hand]), 4 / 3))


def gesture(name, score=0.9):
    result = SimpleNamespace(gestures=[[SimpleNamespace(category_name=name, score=score)]])
    return to_event(result, 0, 0.6)


class FistTests(unittest.TestCase):
    def arm(self, click):
        click.update('Open_Palm', 0)
        click.update('Open_Palm', 0.2)
        self.assertTrue(click.armed)

    def test_initial_fist_and_unknown_cannot_arm(self):
        click = FistClickDetector()
        for now, name in ((0, 'Closed_Fist'), (1, 'Closed_Fist'), (1.1, None), (2, 'Thumb_Up')):
            self.assertFalse(click.update(name, now))
        self.assertFalse(click.armed)

    def test_250_ms_and_one_click_until_confirmed_release(self):
        click = FistClickDetector()
        self.arm(click)
        self.assertFalse(click.update('Closed_Fist', 1))
        self.assertFalse(click.update('Closed_Fist', 1.249))
        self.assertTrue(click.update('Closed_Fist', 1.25))
        for now in (1.5, 2, 3):
            self.assertFalse(click.update('Closed_Fist', now))
        click.update('Open_Palm', 4)
        click.update('Open_Palm', 4.2)
        click.update('Closed_Fist', 5)
        self.assertTrue(click.update('Closed_Fist', 5.25))

    def test_short_oscillation_never_rearms_after_click(self):
        click = FistClickDetector()
        self.arm(click)
        click.update('Closed_Fist', 1)
        self.assertTrue(click.update('Closed_Fist', 1.25))
        click.update('Open_Palm', 1.3)
        self.assertFalse(click.update('Closed_Fist', 1.4))
        click.update(None, 1.5)
        self.assertFalse(click.update('Closed_Fist', 2))
        self.assertFalse(click.armed)

    def test_invalid_gesture_resets_continuous_confirmation(self):
        click = FistClickDetector()
        self.arm(click)
        click.update('Closed_Fist', 1)
        click.update(None, 1.2)
        self.assertFalse(click.update('Closed_Fist', 1.3))
        self.assertFalse(click.update('Closed_Fist', 1.5))
        self.assertTrue(click.update('Closed_Fist', 1.55))

    def test_confirmed_other_accepted_gesture_can_rearm_after_first_opening(self):
        click = FistClickDetector()
        self.arm(click)
        click.update('Closed_Fist', 1)
        click.update('Closed_Fist', 1.25)
        click.update('Thumb_Up', 2)
        click.update('Thumb_Up', 2.2)
        self.assertTrue(click.armed)
        click.reset()
        self.assertFalse(click.armed)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeMouse()
        self.mouse = MouseController(backend=self.backend, smoothing=1)

    def activate(self):
        self.mouse.handle_key(ord('m'))
        self.assertTrue(self.mouse.state.active)

    def arm(self):
        self.activate()
        self.mouse.update(tracking(), gesture('Open_Palm'), now=0)
        self.mouse.update(tracking(), gesture('Open_Palm'), now=0.2)

    def test_starts_disabled_and_m_toggles(self):
        self.mouse.update(tracking(), now=0)
        self.assertFalse(self.mouse.state.active)
        self.assertEqual(self.backend.commands, [])
        self.activate()
        self.mouse.update(tracking(), now=0)
        self.assertEqual(self.backend.commands, [(500, 400, False)])
        self.mouse.handle_key(ord('M'))
        self.assertFalse(self.mouse.state.active)
        self.mouse.update(tracking(), now=1)
        self.assertEqual(len(self.backend.commands), 1)

    def test_esc_cancels_confirmation_and_disables(self):
        self.arm()
        self.mouse.update(tracking(), gesture('Closed_Fist'), now=0.3)
        self.mouse.handle_key(27)
        self.mouse.update(tracking(), gesture('Closed_Fist'), now=0.6)
        self.assertFalse(self.mouse.state.active)
        self.assertFalse(self.backend.active)
        self.assertEqual(self.backend.clicks, 0)

    def test_movement_is_limited_to_15_updates_per_second(self):
        self.activate()
        for index in range(1000):
            self.mouse.update(tracking(), now=index / 1000)
        self.assertLessEqual(len(self.backend.commands), 15)

    def test_fist_click_freezes_position_and_does_not_repeat(self):
        self.arm()
        count = len(self.backend.commands)
        fist = gesture('Closed_Fist')
        self.mouse.update(tracking(point=(0.9, 0.9)), fist, now=0.3)
        self.mouse.update(tracking(point=(0.1, 0.1)), fist, now=0.549)
        self.assertEqual(len(self.backend.commands), count)
        self.mouse.update(tracking(point=(0.9, 0.9)), fist, now=0.55)
        self.assertEqual(self.backend.commands[-1], (500, 400, True))
        for now in (0.6, 0.8, 1):
            self.mouse.update(tracking(), fist, now=now)
        self.assertEqual(self.backend.clicks, 1)
        self.assertEqual(len(self.backend.commands), count + 1)

    def test_low_confidence_fist_cannot_click(self):
        self.arm()
        for now in (0.3, 0.55, 0.8):
            self.mouse.update(tracking(), gesture('Closed_Fist', 0.59), now=now)
        self.assertEqual(self.backend.clicks, 0)

    def test_missing_hand_requires_opening_again(self):
        self.arm()
        self.mouse.update(tracking(), gesture('Closed_Fist'), now=0.3)
        self.mouse.update(None, gesture('Closed_Fist'), now=0.4)
        count = len(self.backend.commands)
        self.mouse.update(None, now=1)
        self.assertEqual(self.mouse.state.status, 'SEM MAO')
        self.assertEqual(len(self.backend.commands), count)
        for now in (1.1, 1.4):
            self.mouse.update(tracking(), gesture('Closed_Fist'), now=now)
        self.assertEqual(self.backend.clicks, 0)

    def test_tracking_gap_does_not_complete_old_fist(self):
        self.arm()
        self.mouse.update(tracking(), gesture('Closed_Fist'), now=0.3)
        self.mouse.update(tracking(), gesture('Closed_Fist'), now=0.9)
        self.assertEqual(self.backend.clicks, 0)

    def test_pending_click_cancels_if_gesture_becomes_invalid(self):
        self.arm()
        self.mouse.update(tracking(), gesture('Closed_Fist'), now=0.3)
        self.backend.accept = False
        self.mouse.update(tracking(), gesture('Closed_Fist'), now=0.55)
        self.backend.accept = True
        self.mouse.update(tracking(), gesture(None), now=0.6)
        self.assertEqual(self.backend.clicks, 0)

    def test_no_mouse_control_does_not_create_or_access_backend(self):
        with patch('hand_control.mouse_control.AsyncMouseBackend') as factory:
            mouse = MouseController(permitted=False)
            mouse.handle_key(ord('m'))
            mouse.update(tracking(), gesture('Closed_Fist'), now=0)
            mouse.handle_key(27)
            mouse.close()
            factory.assert_not_called()
            self.assertIsNone(mouse.backend)
            self.assertFalse(mouse.state.active)

    def test_backend_error_disables_without_changing_other_controllers(self):
        self.activate()
        self.backend.error = 'Mouse indisponivel'
        self.mouse.update(tracking(), now=0)
        self.assertFalse(self.mouse.state.active)
        self.assertIn('indisponivel', self.mouse.state.error)
        self.assertEqual(self.backend.commands, [])


class X11EmissionTests(unittest.TestCase):
    def make_backend(self):
        backend = X11MouseBackend.__new__(X11MouseBackend)
        backend.size = (1366, 768)
        backend.escape = 9
        backend.root = Mock()
        backend.root.query_pointer.return_value = SimpleNamespace(root_x=200, root_y=300)
        backend.display = Mock()
        backend.display.query_keymap.return_value = [0] * 32
        backend.X = SimpleNamespace(MotionNotify=6, ButtonPress=4, ButtonRelease=5)
        backend.xtest = Mock()
        return backend

    def test_x11_motion_bounds_and_balanced_left_click(self):
        backend = self.make_backend()
        self.assertEqual(backend.apply(5000, -10, False, lambda: True), (1365, 0))
        backend.xtest.fake_input.reset_mock()
        self.assertEqual(backend.apply(5000, -10, True, lambda: True), (200, 300))
        calls = backend.xtest.fake_input.call_args_list
        self.assertEqual([call.args[1] for call in calls], [4, 5])
        self.assertEqual(calls[0].args[2], 1)
        self.assertEqual(calls[1].args[2], 1)

    def test_cancelled_job_emits_nothing(self):
        backend = self.make_backend()
        self.assertIsNone(backend.apply(10, 20, True, lambda: False))
        backend.xtest.fake_input.assert_not_called()

    def test_global_esc_and_physical_corner_stop_all_output(self):
        for escape in (False, True):
            backend = self.make_backend()
            if escape:
                keymap = [0] * 32
                keymap[1] = 2
                backend.display.query_keymap.return_value = keymap
            else:
                backend.root.query_pointer.return_value = SimpleNamespace(root_x=0, root_y=0)
            with self.assertRaises(RuntimeError):
                backend.apply(20, 30, True, lambda: True)
            backend.xtest.fake_input.assert_not_called()


class AsyncTests(unittest.TestCase):
    def test_suspended_inflight_job_cannot_click_and_requests_do_not_accumulate(self):
        entered, release = Event(), Event()
        emissions = []
        fake = Mock(size=(1366, 768))

        def apply(x, y, click, allowed):
            entered.set()
            if not release.wait(timeout=2):
                raise RuntimeError('test timeout')
            if allowed():
                emissions.append((x, y, click))
                return x, y
            return None

        fake.apply.side_effect = apply
        backend = AsyncMouseBackend(factory=lambda: fake)
        self.addCleanup(backend.close)
        backend.activate()
        result = backend._results.get(timeout=2)
        backend._results.put(result)
        backend.poll()
        try:
            self.assertTrue(backend.submit(200, 300, True))
            self.assertTrue(entered.wait(timeout=2))
            for _ in range(100):
                self.assertFalse(backend.submit(300, 400, True))
            backend.suspend()
        finally:
            release.set()
        result = backend._results.get(timeout=2)
        self.assertIsNone(result[1])
        self.assertEqual(emissions, [])

    def test_worker_is_lazy_bounded_and_cancels_old_generation(self):
        factory = Mock()
        backend = AsyncMouseBackend(factory=factory)
        factory.assert_not_called()
        self.assertIsNone(backend._thread)
        # Simula um backend pronto, sem iniciar thread/X11.
        backend.size = (1001, 801)
        self.assertTrue(backend.submit(1, 2, False))
        self.assertFalse(backend.submit(3, 4, True))
        self.assertEqual(backend._jobs.qsize(), 1)
        generation = backend._generation
        backend.suspend()
        self.assertGreater(backend._generation, generation)
        self.assertFalse(backend._allowed.is_set())
        backend.close()

    def test_worker_failure_reports_error_without_blocking(self):
        backend = AsyncMouseBackend(factory=Mock(side_effect=RuntimeError('sem X11')))
        self.addCleanup(backend.close)
        backend.activate()
        self.assertTrue(backend._thread.daemon)
        # Espera somente o resultado simulado; não espera por um display real.
        result = backend._results.get(timeout=2)
        backend._results.put(result)
        backend.poll()
        self.assertIn('sem X11', backend.error)
