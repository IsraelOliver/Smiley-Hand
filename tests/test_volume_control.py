"""Todos os subprocessos são simulados; nunca altera o áudio real."""

import subprocess
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from hand_control.gestures import GestureEvent, to_event
from hand_control.virtual_led import VirtualLedController
from hand_control.volume_control import (
    AudioBackend, AudioError, VolumeController, VolumeGestureGate,
)


def event(name):
    return GestureEvent(name, 0.9 if name else 0, 0)


class BackendTests(unittest.TestCase):
    def test_backend_priority_and_missing_tools(self):
        for tools, expected in (({"wpctl": "/usr/bin/wpctl", "pactl": "/usr/bin/pactl"}, "wpctl"),
                                ({"pactl": "/usr/bin/pactl"}, "pactl")):
            with patch("hand_control.volume_control.shutil.which", side_effect=tools.get):
                self.assertEqual(AudioBackend.detect().kind, expected)
        with patch("hand_control.volume_control.shutil.which", return_value=None):
            with self.assertRaises(AudioError):
                AudioBackend.detect()

    def test_wpctl_up_down_and_clamp(self):
        for current, delta, target in ((50, 5, 55), (50, -5, 45), (98, 5, 100),
                                       (2, -5, 0), (120, -5, 100)):
            with self.subTest(current=current, delta=delta):
                backend = AudioBackend("/usr/bin/wpctl", "wpctl")
                with patch("hand_control.volume_control.subprocess.run", side_effect=[
                    SimpleNamespace(stdout=f"Volume: {current / 100:.2f} [MUTED]"),
                    SimpleNamespace(stdout=""),
                    SimpleNamespace(stdout=f"Volume: {target / 100:.2f}"),
                ]) as run:
                    percent, command = backend.adjust(delta)
                self.assertAlmostEqual(percent, target)
                self.assertIsNotNone(command)
                self.assertEqual(run.call_args_list[1].args[0],
                                 ["/usr/bin/wpctl", "set-volume", "-l", "1.0", "@DEFAULT_AUDIO_SINK@", f"{target}%"])
                for call in run.call_args_list:
                    self.assertFalse(call.kwargs["shell"])
                    self.assertEqual(call.kwargs["timeout"], 1)
                    self.assertTrue(call.kwargs["check"])
                    self.assertNotIn("sudo", call.args[0])

    def test_boundaries_do_not_write(self):
        for value, delta in ((100, 5), (0, -5)):
            with patch("hand_control.volume_control.subprocess.run", return_value=SimpleNamespace(stdout=f"Volume: {value / 100:.2f}")) as run:
                self.assertEqual(AudioBackend("wpctl", "wpctl").adjust(delta), (value, None))
                self.assertEqual(run.call_count, 1)

    def test_pactl_clamps_using_largest_channel(self):
        with patch("hand_control.volume_control.subprocess.run", side_effect=[
            SimpleNamespace(stdout="front-left: 60000 / 98% / 0dB, front-right: 50000 / 85% / 0dB"),
            SimpleNamespace(stdout=""), SimpleNamespace(stdout="front-left: 65536 / 100% / 0dB"),
        ]) as run:
            self.assertEqual(AudioBackend("pactl", "pactl").adjust(5)[0], 100)
            self.assertEqual(run.call_args_list[1].args[0],
                             ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "100%"])

    def test_command_errors_timeout_and_bad_response(self):
        for failure in (FileNotFoundError("wpctl"),
                        subprocess.TimeoutExpired(["wpctl"], 1),
                        subprocess.CalledProcessError(1, ["wpctl"], stderr="No default sink")):
            with self.subTest(failure=failure), patch("hand_control.volume_control.subprocess.run", side_effect=failure):
                with self.assertRaises(AudioError):
                    AudioBackend("wpctl", "wpctl").read()
        with patch("hand_control.volume_control.subprocess.run", return_value=SimpleNamespace(stdout="Volume: nan")):
            with self.assertRaises(AudioError):
                AudioBackend("wpctl", "wpctl").read()


class TimingTests(unittest.TestCase):
    def test_confirmation_and_repeats(self):
        gate = VolumeGestureGate()
        self.assertIsNone(gate.update(event("Thumb_Up"), 10))
        self.assertIsNone(gate.update(event("Thumb_Up"), 10.399))
        self.assertEqual(gate.update(event("Thumb_Up"), 10.4), 5)
        self.assertIsNone(gate.update(event("Thumb_Up"), 10.4))
        self.assertIsNone(gate.update(event("Thumb_Up"), 11.099))
        self.assertEqual(gate.update(event("Thumb_Up"), 11.1), 5)

    def test_missing_or_invalid_gesture_restarts_confirmation(self):
        for name in (None, "None", "Victory", "Open_Palm", "Closed_Fist"):
            gate = VolumeGestureGate()
            gate.update(event("Thumb_Down"), 0)
            gate.update(event(name), 0.2)
            gate.update(event("Thumb_Down"), 0.3)
            self.assertIsNone(gate.update(event("Thumb_Down"), 0.5))
            self.assertEqual(gate.update(event("Thumb_Down"), 0.7), -5)

    def test_change_direction_resets_but_preserves_global_cooldown(self):
        gate = VolumeGestureGate()
        gate.update(event("Thumb_Up"), 0)
        self.assertEqual(gate.update(event("Thumb_Up"), 0.4), 5)
        gate.update(event("Thumb_Down"), 0.5)
        self.assertIsNone(gate.update(event("Thumb_Down"), 0.9))
        self.assertEqual(gate.update(event("Thumb_Down"), 1.1), -5)

    def test_low_confidence_cannot_issue_and_resets_confirmation(self):
        gate = VolumeGestureGate()
        result = SimpleNamespace(gestures=[[SimpleNamespace(category_name="Thumb_Up", score=0.4)]])
        gate.update(event("Thumb_Up"), 0)
        self.assertIsNone(gate.update(to_event(result, 200, 0.6), 0.2))
        gate.update(event("Thumb_Up"), 0.3)
        self.assertIsNone(gate.update(event("Thumb_Up"), 0.5))
        self.assertEqual(gate.update(event("Thumb_Up"), 0.7), 5)

    def test_busy_backend_does_not_consume_or_accumulate_commands(self):
        gate = VolumeGestureGate()
        for now in (0, 0.4, 0.8, 2):
            self.assertIsNone(gate.update(event("Thumb_Up"), now, ready=False))
        self.assertEqual(gate.update(event("Thumb_Up"), 2, ready=True), 5)

    def test_led_still_works_and_thumb_does_not_change_it(self):
        led = VirtualLedController()
        gate = VolumeGestureGate()
        for now, name in ((0, "Open_Palm"), (0.3, "Open_Palm"), (0.4, "Thumb_Down"), (0.8, "Thumb_Down")):
            led.update(event(name), now=now)
            gate.update(event(name), now)
        self.assertTrue(led.state.on)
        led.update(event("Closed_Fist"), now=1)
        led.update(event("Closed_Fist"), now=1.3)
        self.assertFalse(led.state.on)


class ControllerTests(unittest.TestCase):
    def make_controller(self, backend=None):
        backend = backend or Mock()
        backend.read.return_value = 50
        backend.adjust.return_value = (55, "Volume +5% -> 55%")
        controller = VolumeController(backend_factory=lambda: backend)
        self.addCleanup(controller.close)
        controller.update(event(None), now=0)
        controller._future.result(timeout=2)
        controller.update(event(None), now=0.01)
        return controller, backend

    def test_disabled_has_no_backend_thread_or_system_calls(self):
        with patch("hand_control.volume_control.subprocess.run") as run, \
             patch("hand_control.volume_control.AudioBackend.detect") as detect, \
             patch("hand_control.volume_control.ThreadPoolExecutor") as executor:
            controller = VolumeController(enabled=False)
            for now in (0, 0.4, 1.1, 10):
                controller.update(event("Thumb_Up"), now=now)
            controller.close()
            run.assert_not_called()
            detect.assert_not_called()
            executor.assert_not_called()

    def test_success_updates_display_and_completion_cooldown(self):
        controller, backend = self.make_controller()
        self.assertTrue(controller.state.available)
        self.assertEqual(controller.state.percent, 50)
        controller.update(event("Thumb_Up"), now=1)
        controller.update(event("Thumb_Up"), now=1.4)
        controller._future.result(timeout=2)
        controller.update(event("Thumb_Up"), now=1.5)
        self.assertEqual(controller.state.percent, 55)
        self.assertEqual(controller.state.last_command, "Volume +5% -> 55%")
        controller.update(event("Thumb_Up"), now=2.199)
        backend.adjust.assert_called_once_with(5)
        controller.update(event("Thumb_Up"), now=2.2)
        controller._future.result(timeout=2)
        self.assertEqual(backend.adjust.call_count, 2)

    def test_unavailable_backend_is_reported_and_retries_are_bounded(self):
        factory = Mock(side_effect=AudioError("sem saida de audio"))
        controller = VolumeController(backend_factory=factory)
        self.addCleanup(controller.close)
        controller.update(event(None), now=0)
        with self.assertRaises(AudioError):
            controller._future.result(timeout=2)
        controller.update(event(None), now=0.01)
        self.assertFalse(controller.state.available)
        self.assertIn("sem saida", controller.state.error)
        for now in (0.4, 0.8, 1.0, 1.9):
            controller.update(event("Thumb_Up"), now=now)
        factory.assert_called_once()

    def test_only_one_operation_can_be_in_flight(self):
        controller, backend = self.make_controller()
        started, release = Event(), Event()

        def blocked_adjust(delta):
            started.set()
            if not release.wait(timeout=2):
                raise AudioError("test timeout")
            return 55, "Volume +5% -> 55%"

        backend.adjust.side_effect = blocked_adjust
        try:
            controller.update(event("Thumb_Up"), now=1)
            controller.update(event("Thumb_Up"), now=1.4)
            self.assertTrue(started.wait(timeout=2))
            future = controller._future
            for index in range(100):
                controller.update(event("Thumb_Up"), now=2 + index / 100)
            self.assertIs(controller._future, future)
            backend.adjust.assert_called_once_with(5)
        finally:
            release.set()
        controller._future.result(timeout=2)
