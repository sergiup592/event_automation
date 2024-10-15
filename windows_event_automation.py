import sys
import time
import logging
from pynput import keyboard as pynput_keyboard
from pynput import mouse as pynput_mouse
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout,
    QHBoxLayout, QSpinBox, QProgressBar, QMessageBox
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QObject

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='macro_recorder.log',
    filemode='w'  # Overwrite log file on each run
)

class MacroRecorder(QThread):
    finished = pyqtSignal()
    status_update = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.recording = False
        self.actions = []
        self.start_time = None
        self.last_action_time = None  # To track the absolute time of the last action
        self.keyboard_listener = None
        self.mouse_listener = None

    def run(self):
        self.recording = True
        self.start_time = time.time()
        self.last_action_time = self.start_time  # Initialize last_action_time
        self.status_update.emit("Recording Started")
        logging.info("Recording Started")

        # Set up listeners using context managers to ensure proper cleanup
        with pynput_keyboard.Listener(
            on_press=self.on_key_press,
            on_release=self.on_key_release
        ) as self.keyboard_listener, \
             pynput_mouse.Listener(
                 on_move=self.on_mouse_move,
                 on_click=self.on_mouse_click,
                 on_scroll=self.on_mouse_scroll
             ) as self.mouse_listener:
            try:
                while self.recording:
                    time.sleep(0.01)
            except Exception as e:
                logging.error(f"Recording Error: {e}")
                self.status_update.emit(f"Recording Error: {e}")
            finally:
                self.recording = False
                self.status_update.emit("Recording Finished")
                logging.info("Recording Finished")
                self.finished.emit()

    def stop(self):
        self.recording = False

    def on_key_press(self, key):
        if not self.recording:
            return
        current_time = time.time()
        delta = current_time - self.last_action_time
        self.last_action_time = current_time
        key_name = self.get_key_name(key)
        self.actions.append(('key_down', key_name, delta))
        logging.debug(f"Key Pressed: {key_name} | Delta Time: {delta}")

    def on_key_release(self, key):
        if not self.recording:
            return
        current_time = time.time()
        delta = current_time - self.last_action_time
        self.last_action_time = current_time
        key_name = self.get_key_name(key)
        self.actions.append(('key_up', key_name, delta))
        logging.debug(f"Key Released: {key_name} | Delta Time: {delta}")

    def on_mouse_move(self, x, y):
        if not self.recording:
            return
        current_time = time.time()
        delta = current_time - self.last_action_time
        self.last_action_time = current_time
        self.actions.append(('move', x, y, delta))
        logging.debug(f"Mouse Moved to ({x}, {y}) | Delta Time: {delta}")

    def on_mouse_click(self, x, y, button, pressed):
        if not self.recording:
            return
        current_time = time.time()
        delta = current_time - self.last_action_time
        self.last_action_time = current_time
        action = 'mouse_down' if pressed else 'mouse_up'
        self.actions.append((action, button.name, x, y, delta))
        logging.debug(f"Mouse {'Pressed' if pressed else 'Released'}: {button.name} at ({x}, {y}) | Delta Time: {delta}")

    def on_mouse_scroll(self, x, y, dx, dy):
        if not self.recording:
            return
        current_time = time.time()
        delta = current_time - self.last_action_time
        self.last_action_time = current_time
        self.actions.append(('scroll', dx, dy, delta))
        logging.debug(f"Mouse Scrolled: dx={dx}, dy={dy} at ({x}, {y}) | Delta Time: {delta}")

    @staticmethod
    def get_key_name(key):
        try:
            return key.char
        except AttributeError:
            return str(key).replace('Key.', '')

class MacroPlayer(QThread):
    finished = pyqtSignal()
    progress_update = pyqtSignal(int)
    status_update = pyqtSignal(str)

    def __init__(self, actions, repeat_count):
        super().__init__()
        self.actions = actions
        self.repeat_count = repeat_count
        self.is_playing = True
        self.pressed_keys = set()
        self.pressed_buttons = set()

    def run(self):
        self.status_update.emit("Playing Macro")
        logging.info("Playback Started")
        keyboard_controller = pynput_keyboard.Controller()
        mouse_controller = pynput_mouse.Controller()

        try:
            for i in range(self.repeat_count):
                if not self.is_playing:
                    logging.info("Playback Stopped by User")
                    break
                logging.info(f"Starting iteration {i + 1} of {self.repeat_count}")
                for action in self.actions:
                    if not self.is_playing:
                        logging.info("Playback Stopped by User during iteration")
                        break
                    action_type = action[0]
                    delta_time = action[-1]
                    if delta_time > 0:
                        time.sleep(delta_time)
                    self.execute_action(action, keyboard_controller, mouse_controller)
                self.progress_update.emit(i + 1)
                logging.info(f"Completed iteration {i + 1} of {self.repeat_count}")
            if self.is_playing:
                self.status_update.emit("Playback Finished")
                logging.info("Playback Finished Successfully")
            else:
                self.status_update.emit("Playback Stopped")
        except Exception as e:
            logging.error(f"Playback Error: {e}")
            self.status_update.emit(f"Playback Error: {e}")
        finally:
            # Release any remaining pressed keys and buttons
            self.release_all(keyboard_controller, mouse_controller)
            self.finished.emit()

    def stop_playback(self):
        self.is_playing = False

    def execute_action(self, action, keyboard_controller, mouse_controller):
        action_type = action[0]
        if action_type in ['key_down', 'key_up']:
            key = self.get_key(action[1])
            if key is None:
                logging.warning(f"Unrecognized key: {action[1]}")
                return
            if action_type == 'key_down':
                keyboard_controller.press(key)
                self.pressed_keys.add(key)
                logging.debug(f"Key Pressed: {action[1]}")
            else:
                keyboard_controller.release(key)
                self.pressed_keys.discard(key)
                logging.debug(f"Key Released: {action[1]}")
        elif action_type == 'move':
            _, x, y, _ = action
            mouse_controller.position = (x, y)
            logging.debug(f"Mouse Moved to ({x}, {y})")
        elif action_type in ['mouse_down', 'mouse_up']:
            button = self.get_button(action[1])
            if button is None:
                logging.warning(f"Unrecognized mouse button: {action[1]}")
                return
            if action_type == 'mouse_down':
                mouse_controller.press(button)
                self.pressed_buttons.add(button)
                logging.debug(f"Mouse Button Pressed: {action[1]}")
            else:
                mouse_controller.release(button)
                self.pressed_buttons.discard(button)
                logging.debug(f"Mouse Button Released: {action[1]}")
        elif action_type == 'scroll':
            _, dx, dy, _ = action
            mouse_controller.scroll(dx, dy)
            logging.debug(f"Mouse Scrolled: dx={dx}, dy={dy}")
        else:
            logging.warning(f"Unknown action type: {action_type}")

    def release_all(self, keyboard_controller, mouse_controller):
        logging.info("Releasing all pressed keys and mouse buttons")
        for key in list(self.pressed_keys):
            keyboard_controller.release(key)
            logging.debug(f"Released Key: {key}")
        for button in list(self.pressed_buttons):
            mouse_controller.release(button)
            logging.debug(f"Released Mouse Button: {button}")
        self.pressed_keys.clear()
        self.pressed_buttons.clear()

    @staticmethod
    def get_key(key_name):
        try:
            if len(key_name) == 1:
                return key_name
            return getattr(pynput_keyboard.Key, key_name.lower())
        except AttributeError:
            logging.error(f"Key mapping failed for: {key_name}")
            return None  # Return None to indicate an unmapped key

    @staticmethod
    def get_button(button_name):
        try:
            return getattr(pynput_mouse.Button, button_name)
        except AttributeError:
            logging.error(f"Button mapping failed for: {button_name}")
            return None  # Return None to indicate an unmapped button

class HotkeyListener(QObject):
    # Define signals for each hotkey
    start_recording_signal = pyqtSignal()
    stop_recording_signal = pyqtSignal()
    start_playback_signal = pyqtSignal()
    stop_playback_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.listener = pynput_keyboard.GlobalHotKeys({
            '<ctrl>+z': self.start_recording,
            '<ctrl>+x': self.stop_recording,
            '<ctrl>+c': self.start_playback,
            '<ctrl>+v': self.stop_playback
        })

    def start_listener(self):
        self.listener.start()
        logging.info("Global hotkey listener started")

    def stop_listener(self):
        self.listener.stop()
        logging.info("Global hotkey listener stopped")

    def start_recording(self):
        logging.info("Hotkey Triggered: Start Recording")
        self.start_recording_signal.emit()

    def stop_recording(self):
        logging.info("Hotkey Triggered: Stop Recording")
        self.stop_recording_signal.emit()

    def start_playback(self):
        logging.info("Hotkey Triggered: Start Playback")
        self.start_playback_signal.emit()

    def stop_playback(self):
        logging.info("Hotkey Triggered: Stop Playback")
        self.stop_playback_signal.emit()

class MacroRecorderGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.macro_recorder = None
        self.macro_player = None
        self.recorded_actions = []
        self.hotkey_listener = HotkeyListener()

        # Connect hotkey signals to GUI slots
        self.hotkey_listener.start_recording_signal.connect(self.start_recording)
        self.hotkey_listener.stop_recording_signal.connect(self.stop_recording)
        self.hotkey_listener.start_playback_signal.connect(self.play_macro)
        self.hotkey_listener.stop_playback_signal.connect(self.stop_macro)

        # Start the hotkey listener
        self.hotkey_listener.start_listener()

    def initUI(self):
        self.setWindowTitle('Macro Recorder')
        self.setGeometry(100, 100, 400, 250)
        self.setFixedSize(400, 250)  # Fixed window size for consistency

        main_layout = QVBoxLayout()

        # Status Label
        self.status_label = QLabel('Status: Ready')
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)

        # Shortcuts Information
        shortcuts_group = QWidget()
        shortcuts_layout = QVBoxLayout()
        shortcuts_group.setLayout(shortcuts_layout)

        shortcuts_title = QLabel('Global Keyboard Shortcuts:')
        shortcuts_title.setStyleSheet("font-weight: bold;")
        shortcuts_layout.addWidget(shortcuts_title)

        shortcuts = [
            ('Start Recording', 'Ctrl + Z'),
            ('Stop Recording', 'Ctrl + X'),
            ('Start Replay', 'Ctrl + C'),
            ('Stop Replay', 'Ctrl + V')
        ]

        for action, shortcut in shortcuts:
            shortcut_label = QLabel(f"{action}: {shortcut}")
            shortcuts_layout.addWidget(shortcut_label)

        main_layout.addWidget(shortcuts_group)

        # Repeat Count Selection
        repeat_layout = QHBoxLayout()
        repeat_label = QLabel('Repeat Count:')
        self.repeat_spinbox = QSpinBox()
        self.repeat_spinbox.setRange(1, 100000)
        self.repeat_spinbox.setValue(1)

        # Ensure the spin box is enabled and can receive focus
        self.repeat_spinbox.setEnabled(True)
        self.repeat_spinbox.setFocusPolicy(Qt.StrongFocus)

        # Optional: Set a tooltip to guide users
        self.repeat_spinbox.setToolTip("Enter the number of times to repeat the macro.")

        repeat_layout.addWidget(repeat_label)
        repeat_layout.addWidget(self.repeat_spinbox)
        main_layout.addLayout(repeat_layout)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)  # Will be updated dynamically
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        self.setLayout(main_layout)

    def start_recording(self):
        if self.macro_recorder and self.macro_recorder.isRunning():
            QMessageBox.warning(self, "Warning", "Recording is already in progress.")
            return

        # Ensure any previous recorder is stopped
        if self.macro_recorder:
            self.macro_recorder.stop()
            self.macro_recorder.wait()

        self.macro_recorder = MacroRecorder()
        self.macro_recorder.finished.connect(self.on_recording_finished)
        self.macro_recorder.status_update.connect(self.update_status)
        self.macro_recorder.start()
        self.update_status("Recording Started")
        logging.info("Recording started via GUI")

    def stop_recording(self):
        if not self.macro_recorder or not self.macro_recorder.isRunning():
            QMessageBox.warning(self, "Warning", "No recording is in progress.")
            return

        self.macro_recorder.stop()
        self.update_status("Stopping Recording...")
        logging.info("Stopping recording via GUI")

    def on_recording_finished(self):
        self.update_status("Recording Finished")
        self.recorded_actions = self.macro_recorder.actions.copy()
        logging.info(f"Recorded Actions: {len(self.recorded_actions)} actions recorded")
        self.macro_recorder = None

    def play_macro(self):
        if not self.recorded_actions:
            QMessageBox.information(self, "Info", "No recorded actions to play.")
            return

        if self.macro_player and self.macro_player.isRunning():
            QMessageBox.warning(self, "Warning", "Playback is already in progress.")
            return

        repeat_count = self.repeat_spinbox.value()
        self.macro_player = MacroPlayer(self.recorded_actions, repeat_count)
        self.macro_player.finished.connect(self.on_playback_finished)
        self.macro_player.progress_update.connect(self.update_progress)
        self.macro_player.status_update.connect(self.update_status)
        self.macro_player.start()
        self.progress_bar.setMaximum(repeat_count)
        self.progress_bar.setValue(0)
        self.update_status("Playback Started")
        logging.info(f"Playback started with repeat count: {repeat_count}")

    def stop_macro(self):
        if not self.macro_player or not self.macro_player.isRunning():
            QMessageBox.warning(self, "Warning", "No playback is in progress.")
            return

        self.macro_player.stop_playback()
        self.update_status("Stopping Playback...")
        logging.info("Stopping playback via GUI")

    def on_playback_finished(self):
        self.update_status("Playback Finished")
        self.progress_bar.setValue(0)
        logging.info("Playback finished")
        self.macro_player = None

    def update_progress(self, value):
        self.progress_bar.setValue(value)
        logging.debug(f"Playback Progress: {value}/{self.repeat_spinbox.value()}")

    def update_status(self, status):
        self.status_label.setText(f"Status: {status}")
        logging.info(f"Status Updated: {status}")

    def closeEvent(self, event):
        # Cleanup threads on exit
        logging.info("Application closing. Cleaning up resources.")
        if self.macro_recorder and self.macro_recorder.isRunning():
            self.macro_recorder.stop()
            self.macro_recorder.wait()
            logging.info("Stopped macro recorder thread on exit.")
        if self.macro_player and self.macro_player.isRunning():
            self.macro_player.stop_playback()
            self.macro_player.wait()
            logging.info("Stopped macro player thread on exit.")
        # Stop the hotkey listener
        if self.hotkey_listener:
            self.hotkey_listener.stop_listener()
        event.accept()

def main():
    app = QApplication(sys.argv)
    gui = MacroRecorderGUI()
    gui.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()