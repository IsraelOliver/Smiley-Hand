"""Confirmação temporal determinística, sem webcam e sem esperas reais."""

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from hand_control.gestures import GestureEvent, to_event
from hand_control.virtual_led import LedCommand, LedState, VirtualLedController


def event(name):
    return GestureEvent(name, 0.9 if name else 0.0, 0)


class VirtualLedTests(unittest.TestCase):
    def setUp(self):
        self.output = Mock()
        self.led = VirtualLedController(output=self.output)

    def turn_on(self):
        self.led.update(event("Open_Palm"), now=10.0)
        self.assertEqual(self.led.update(event("Open_Palm"), now=10.3), LedCommand.ON)

    def test_initial_state_is_off_without_commands(self):
        self.assertEqual(self.led.state, LedState(on=False))
        self.output.send.assert_not_called()

    def test_open_palm_requires_full_300_ms(self):
        self.assertIsNone(self.led.update(event("Open_Palm"), now=10.0))
        self.assertIsNone(self.led.update(event("Open_Palm"), now=10.15))
        self.assertAlmostEqual(self.led.state.progress, 0.5)
        self.assertEqual(self.led.state.pending_gesture, "Open_Palm")
        self.assertIsNone(self.led.update(event("Open_Palm"), now=10.299))
        self.assertFalse(self.led.state.on)
        self.assertEqual(self.led.update(event("Open_Palm"), now=10.3), LedCommand.ON)
        self.assertEqual(self.led.state, LedState(on=True))
        self.output.send.assert_called_once_with(LedCommand.ON)

    def test_closed_fist_requires_full_300_ms_to_turn_off(self):
        self.turn_on()
        self.assertIsNone(self.led.update(event("Closed_Fist"), now=11.0))
        self.assertIsNone(self.led.update(event("Closed_Fist"), now=11.299))
        self.assertTrue(self.led.state.on)
        self.assertEqual(self.led.update(event("Closed_Fist"), now=11.3), LedCommand.OFF)
        self.assertFalse(self.led.state.on)
        self.assertEqual([c.args[0] for c in self.output.send.call_args_list],
                         [LedCommand.ON, LedCommand.OFF])

    def test_unstable_gesture_restarts_confirmation(self):
        self.led.update(event("Open_Palm"), now=0.0)
        self.led.update(event("Closed_Fist"), now=0.2)
        self.led.update(event("Open_Palm"), now=0.25)
        self.assertIsNone(self.led.update(event("Open_Palm"), now=0.4))
        self.assertFalse(self.led.state.on)
        self.assertAlmostEqual(self.led.state.progress, 0.5)
        self.output.send.assert_not_called()
        self.assertEqual(self.led.update(event("Open_Palm"), now=0.55), LedCommand.ON)

    def test_invalid_events_reset_pending_but_keep_last_state(self):
        for invalid in (None, "None", "Unknown", "Thumb_Up"):
            with self.subTest(invalid=invalid):
                led = VirtualLedController()
                led.update(event("Open_Palm"), now=0.0)
                led.update(event(invalid), now=0.2)
                self.assertEqual(led.state, LedState(on=False))
                led.update(event("Open_Palm"), now=0.25)
                self.assertIsNone(led.update(event("Open_Palm"), now=0.4))
                self.assertFalse(led.state.on)
                led.update(event("Open_Palm"), now=0.55)
                self.assertTrue(led.state.on)
                led.update(event("Closed_Fist"), now=1.0)
                led.update(event(invalid), now=1.2)
                self.assertEqual(led.state, LedState(on=True))

    def test_below_threshold_gesture_cannot_change_led(self):
        for on, name in ((False, "Open_Palm"), (True, "Closed_Fist")):
            with self.subTest(on=on):
                led = VirtualLedController()
                if on:
                    led.update(event("Open_Palm"), now=0.0)
                    led.update(event("Open_Palm"), now=0.3)
                result = SimpleNamespace(gestures=[[
                    SimpleNamespace(category_name=name, score=0.59)
                ]], hand_landmarks=[object()])
                for now in (1.0, 1.3, 2.0):
                    self.assertIsNone(led.update(to_event(result, int(now * 1000), 0.6), now=now))
                    self.assertEqual(led.state, LedState(on=on))

    def test_confidence_drop_restarts_full_confirmation(self):
        self.led.update(event("Open_Palm"), now=0)
        result = SimpleNamespace(gestures=[[
            SimpleNamespace(category_name="Open_Palm", score=0.4)
        ]])
        self.led.update(to_event(result, 200, 0.6), now=0.2)
        self.led.update(event("Open_Palm"), now=0.25)
        self.assertIsNone(self.led.update(event("Open_Palm"), now=0.4))
        self.assertFalse(self.led.state.on)
        self.output.send.assert_not_called()

    def test_missing_hand_holds_last_state(self):
        self.turn_on()
        no_hand = SimpleNamespace(gestures=[], hand_landmarks=[])
        for now in (11.0, 12.0, 20.0):
            self.led.update(to_event(no_hand, int(now * 1000), 0.6), now=now)
            self.assertEqual(self.led.state, LedState(on=True))
        self.output.send.assert_called_once_with(LedCommand.ON)

    def test_repeated_commands_are_not_emitted(self):
        for now in (0, 0.3, 0.6):
            self.led.update(event("Closed_Fist"), now=now)
        self.output.send.assert_not_called()
        self.turn_on()
        for now in (11, 12, 13):
            self.assertIsNone(self.led.update(event("Open_Palm"), now=now))
            self.assertEqual(self.led.state, LedState(on=True))
        self.led.update(event("Closed_Fist"), now=14)
        self.led.update(event("Closed_Fist"), now=14.3)
        for now in (15, 16):
            self.assertIsNone(self.led.update(event("Closed_Fist"), now=now))
        self.assertEqual(self.output.send.call_count, 2)

    def test_default_clock_is_time_monotonic(self):
        with patch("hand_control.virtual_led.time.monotonic", side_effect=[20, 20.15, 20.3]):
            self.led.update(event("Open_Palm"))
            self.led.update(event("Open_Palm"))
            self.assertAlmostEqual(self.led.state.progress, 0.5)
            self.assertEqual(self.led.update(event("Open_Palm")), LedCommand.ON)
