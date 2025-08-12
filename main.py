import json
import os
import sys

from PyQt5.QtCore import Qt, QRegExp, QSettings, QTimer, QSize
from PyQt5.QtGui import (
    QKeySequence, QColor, QTextCharFormat, QSyntaxHighlighter, QTextCursor, QFont, QPalette,
    QTextDocument, QIcon, QPixmap
)
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QAction, QFileDialog, QMessageBox, QTreeWidget, QTreeWidgetItem,
    QTabWidget, QWidget, QVBoxLayout, QTextEdit, QPushButton, QLabel, QLineEdit, QHBoxLayout,
    QToolBar, QStyleFactory, QShortcut, QStatusBar, QDockWidget,
    QMenu, QToolButton
)


class JsonHighlighter(QSyntaxHighlighter):
    """
    Syntax highlighter for JSON text.
    Highlights keywords, numbers, strings, and object keys with different colors.
    Supports light and dark themes.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rules = []
        self._rules_compiled = []

        self.dark_theme_colors = {
            "keyword": QColor("#569cd6"),
            "number": QColor("#b5cea8"),
            "string": QColor("#ce9178"),
            "string_key": QColor("#9cdcfe"),
        }
        self.light_theme_colors = {
            "keyword": QColor("#0000FF"),
            "number": QColor("#800080"),
            "string": QColor("#008000"),
            "string_key": QColor("#000080"),
        }
        self.formats = {}
        self.set_theme("light")

        patterns = [
            (r'"[a-zA-Z0-9_]+"\s*:', "string_key"),
            (r'\b(true|false|null)\b', "keyword"),
            (r'\b[-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?\b', "number"),
            (r'"[^"\\]*(?:\\.[^"\\]*)*"', "string_value")
        ]

        for pattern, fmt_key in patterns:
            self._rules_compiled.append((QRegExp(pattern), fmt_key))

    def set_theme(self, mode):
        """
        Sets the color theme for the highlighter and rehighlights the document.
        """
        colors = self.dark_theme_colors if mode == "dark" else self.light_theme_colors

        self.formats["keyword"] = QTextCharFormat()
        self.formats["keyword"].setForeground(colors["keyword"])

        self.formats["number"] = QTextCharFormat()
        self.formats["number"].setForeground(colors["number"])

        self.formats["string_key"] = QTextCharFormat()
        self.formats["string_key"].setForeground(colors["string_key"])

        self.formats["string_value"] = QTextCharFormat()
        self.formats["string_value"].setForeground(colors["string"])

        self.rehighlight()

    def highlightBlock(self, text):
        """
        Applies highlighting to a single block of text.
        Uses pre-compiled regular expressions.
        """
        for expression, fmt_key in self._rules_compiled:
            index = expression.indexIn(text)
            while index >= 0:
                length = expression.matchedLength()
                self.setFormat(index, length, self.formats.get(fmt_key))
                index = expression.indexIn(text, index + length)


class JsonTab(QWidget):
    """
    Represents a single tab in the JSON editor, containing an editor
    and a tree view.
    """

    def __init__(self, filename=None, content=""):
        super().__init__()
        self.filename = filename
        self.modified = False
        self.is_valid = True
        self.json_data = None
        self._last_json_error = None

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.main_tab_widget = QTabWidget()

        self.editor = QTextEdit()
        self.editor.blockSignals(True)
        self.editor.setPlainText(content)
        self.editor.blockSignals(False)
        self.modified = False

        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setTabStopWidth(4 * self.editor.fontMetrics().width(' '))
        self.highlighter = JsonHighlighter(self.editor.document())

        self.update_timer = QTimer(self)
        self.update_timer.setSingleShot(True)
        self.update_timer.setInterval(300)
        self.editor.textChanged.connect(self.update_timer.start)
        self.update_timer.timeout.connect(self.update_views)

        self.editor.textChanged.connect(self.mark_modified)
        self.main_tab_widget.addTab(self.editor, "Editor")

        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["Key", "Value"])
        self.tree_widget.itemDoubleClicked.connect(self.navigate_to_key)
        self.tree_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self.show_context_menu)
        self.main_tab_widget.addTab(self.tree_widget, "Tree View")

        self.layout.addWidget(self.main_tab_widget)

        self.control_panel = QWidget()
        self.control_layout = QHBoxLayout(self.control_panel)
        self.control_layout.setContentsMargins(0, 0, 0, 0)

        self.pretty_button = QPushButton("Format JSON")
        self.pretty_button.clicked.connect(self.pretty_print)
        self.minify_button = QPushButton("Minify JSON")
        self.minify_button.clicked.connect(self.minify)

        self.control_layout.addWidget(self.pretty_button)
        self.control_layout.addWidget(self.minify_button)
        self.layout.addWidget(self.control_panel)

        self.update_views()

    def update_views(self):
        """
        Parses the JSON in the editor and updates the Tree View.
        Handles invalid JSON by displaying an error in the tree view, which is expected behavior
        when non-JSON text is pasted or typed. This method is now debounced.
        """
        self.is_valid = True
        self._last_json_error = None
        try:
            self.json_data = json.loads(self.editor.toPlainText())
            self.build_tree(self.tree_widget, self.json_data)
        except json.JSONDecodeError as e:
            self.is_valid = False
            self.json_data = None
            self._last_json_error = e
            self.tree_widget.clear()
            error_item = QTreeWidgetItem(self.tree_widget)
            error_item.setText(0, "Invalid JSON")
            error_item.setText(1, str(e))
            self.tree_widget.addTopLevelItem(error_item)

    def build_tree(self, parent_widget, data):
        """
        Clears the tree widget and builds it recursively from the JSON data.
        """
        parent_widget.clear()
        self._build_tree_recursive(parent_widget, data)

    def _build_tree_recursive(self, parent_item, data):
        """
        Helper function to recursively build the QTreeWidget items.
        Stores the full path of each item for navigation.
        """
        if isinstance(data, dict):
            for key, value in data.items():
                item = QTreeWidgetItem(parent_item)
                item.setText(0, str(key))
                item.setText(1, str(type(value).__name__))
                item.setData(1, Qt.UserRole, value if not isinstance(value, (dict, list)) else None)
                self._build_tree_recursive(item, value)
        elif isinstance(data, list):
            for i, value in enumerate(data):
                item = QTreeWidgetItem(parent_item)
                item.setText(0, f"[{i}]")
                item.setText(1, str(type(value).__name__))
                item.setData(1, Qt.UserRole, value if not isinstance(value, (dict, list)) else None)
                self._build_tree_recursive(item, value)
        else:
            parent_item.setText(1, str(data))
            parent_item.setData(1, Qt.UserRole, data)

    def navigate_to_key(self, item):
        """
        When an item in the tree view is double-clicked,
        finds and highlights the corresponding text in the editor using the SearchPanel.
        This operation should not mark the file as modified.
        """
        search_term = ""
        if item.childCount() > 0:
            if item.text(0).startswith('['):
                search_term = str(item.data(1, Qt.UserRole) if item.data(1, Qt.UserRole) is not None else item.text(1))
            else:
                search_term = f'"{item.text(0)}"'
        else:
            search_term = str(item.data(1, Qt.UserRole) if item.data(1, Qt.UserRole) is not None else item.text(1))

        if not search_term:
            return

        main_window = self.parent().parent()
        if isinstance(main_window, QMainWindow) and hasattr(main_window, 'search_panel'):
            search_panel = main_window.search_panel
            search_panel.search_box.setText(search_term)
            self.main_tab_widget.setCurrentIndex(0)

    def show_context_menu(self, position):
        """
        Displays a context menu for the tree view items (e.g., Copy Key, Copy Value).
        """
        item = self.tree_widget.itemAt(position)
        if not item:
            return

        menu = QMenu()
        copy_key_action = QAction("Copy Key", self)
        copy_key_action.triggered.connect(lambda: QApplication.clipboard().setText(item.text(0)))
        menu.addAction(copy_key_action)

        copy_value_action = QAction("Copy Value", self)
        value_to_copy = str(item.data(1, Qt.UserRole) if item.data(1, Qt.UserRole) is not None else item.text(1))
        copy_value_action.triggered.connect(lambda: QApplication.clipboard().setText(value_to_copy))
        menu.addAction(copy_value_action)

        menu.exec_(self.tree_widget.mapToGlobal(position))

    def mark_modified(self):
        """
        Marks the tab as modified and updates its title with an asterisk.
        This function now only updates the tab text if the modified status
        is changing from False to True. Signals are blocked in other methods
        to prevent false positives.
        """
        if not self.modified:
            self.modified = True
            tab_widget = self.parent().parent()
            tab_widget.setTabText(tab_widget.indexOf(self),
                                  os.path.basename(self.filename) + " *" if self.filename else "Untitled *")

    def pretty_print(self):
        """
        Formats the JSON content in the editor with an indent of 4 spaces.
        """
        try:
            if not self.json_data:
                self.json_data = json.loads(self.editor.toPlainText())

            formatted_text = json.dumps(self.json_data, indent=4)

            if self.editor.toPlainText() != formatted_text:
                self.editor.blockSignals(True)
                self.editor.setPlainText(formatted_text)
                self.editor.blockSignals(False)
                self.modified = True
                tab_widget = self.parent().parent()
                tab_widget.setTabText(tab_widget.indexOf(self),
                                      os.path.basename(self.filename) + " *" if self.filename else "Untitled *")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Invalid JSON: {e}")

    def minify(self):
        """
        Minifies the JSON content in the editor (removes whitespace).
        """
        try:
            if not self.json_data:
                self.json_data = json.loads(self.editor.toPlainText())

            minified_text = json.dumps(self.json_data, separators=(',', ':'))

            if self.editor.toPlainText() != minified_text:
                self.editor.blockSignals(True)
                self.editor.setPlainText(minified_text)
                self.editor.blockSignals(False)
                self.modified = True
                tab_widget = self.parent().parent()
                tab_widget.setTabText(tab_widget.indexOf(self),
                                      os.path.basename(self.filename) + " *" if self.filename else "Untitled *")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Invalid JSON: {e}")

    def save(self):
        """
        Saves the content of the current tab to its associated file.
        Prompts for a filename if it's a new, unsaved file.
        Includes options for force save and showing errors if JSON is invalid.
        """
        if not self.is_valid:
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setWindowTitle("Invalid JSON")
            msg_box.setText("The current JSON is invalid.")
            msg_box.setInformativeText("Do you want to force save it anyway or view the errors?")

            save_button = msg_box.addButton("Save Anyway", QMessageBox.AcceptRole)
            show_errors_button = msg_box.addButton("Show Errors", QMessageBox.ActionRole)
            cancel_button = msg_box.addButton("Cancel", QMessageBox.RejectRole)

            msg_box.setDefaultButton(cancel_button)

            msg_box.exec_()

            clicked_button = msg_box.clickedButton()

            if clicked_button == save_button:
                pass
            elif clicked_button == show_errors_button:
                if self._last_json_error:
                    self.show_json_error(self._last_json_error)
                else:
                    QMessageBox.information(self, "No Specific Error",
                                            "No specific JSON parsing error details available.")
                return False
            else:
                return False

        if not self.filename:
            return self.save_as()
        try:
            with open(self.filename, 'w') as f:
                f.write(self.editor.toPlainText())
            self.modified = False
            tab_widget = self.parent().parent()
            tab_widget.setTabText(tab_widget.indexOf(self), os.path.basename(self.filename))
            return True
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            return False

    def save_as(self):
        """
        Prompts the user to choose a new filename and saves the content.
        """
        filename, _ = QFileDialog.getSaveFileName(self, "Save JSON", "", "JSON Files (*.json)")
        if filename:
            self.filename = filename
            return self.save()
        return False

    def show_json_error(self, error: json.JSONDecodeError):
        """
        Navigates to the line and column of a JSONDecodeError and highlights it.
        """
        editor = self.editor
        self.main_tab_widget.setCurrentIndex(0)

        editor.setExtraSelections([])

        if error.lineno is None or error.colno is None:
            QMessageBox.warning(self, "Error Location", f"Could not determine specific error location for: {error.msg}")
            return

        cursor = QTextCursor(editor.document())

        block = editor.document().findBlockByLineNumber(error.lineno - 1)
        if not block.isValid():
            QMessageBox.warning(self, "Error Location", f"Could not find line {error.lineno}.")
            return

        cursor.setPosition(block.position() + error.colno - 1)
        cursor.movePosition(QTextCursor.NextCharacter, QTextCursor.KeepAnchor, 1)

        selection = QTextEdit.ExtraSelection()
        selection.cursor = cursor
        error_format = QTextCharFormat()
        error_format.setBackground(QColor(255, 100, 100, 150))
        selection.format = error_format

        editor.setExtraSelections([selection])
        editor.setTextCursor(cursor)
        editor.ensureCursorVisible()


class SearchPanel(QDockWidget):
    """
    A dockable widget for finding and replacing text within the JSON editor.
    """

    def __init__(self, parent=None):
        super().__init__("Find/Replace", parent)

        self.widget = QWidget()
        self.layout = QVBoxLayout(self.widget)
        self.layout.setContentsMargins(5, 5, 5, 5)

        find_layout = QHBoxLayout()
        find_layout.addWidget(QLabel("Find:"))
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Enter search term...")
        self.search_box.textChanged.connect(self.on_search_box_changed)
        self.search_box.returnPressed.connect(self.find_next)
        find_layout.addWidget(self.search_box)
        self.find_prev_button = QPushButton("Prev")
        self.find_prev_button.clicked.connect(self.find_prev)
        find_layout.addWidget(self.find_prev_button)
        self.find_next_button = QPushButton("Next")
        self.find_next_button.clicked.connect(self.find_next)
        find_layout.addWidget(self.find_next_button)
        self.layout.addLayout(find_layout)

        replace_layout = QHBoxLayout()
        replace_layout.addWidget(QLabel("Replace:"))
        self.replace_box = QLineEdit()
        self.replace_box.setPlaceholderText("Replace with...")
        replace_layout.addWidget(self.replace_box)
        self.replace_button = QPushButton("Replace")
        self.replace_button.clicked.connect(self.replace_current)
        replace_layout.addWidget(self.replace_button)
        self.replace_all_button = QPushButton("Replace All")
        self.replace_all_button.clicked.connect(self.replace_all)
        replace_layout.addWidget(self.replace_all_button)
        self.layout.addLayout(replace_layout)
        status_layout = QHBoxLayout()
        self.match_count_label = QLabel("No matches")
        status_layout.addWidget(self.match_count_label)
        status_layout.addStretch(1)
        self.close_button = QToolButton()
        self.close_button.setText("X")
        self.close_button.clicked.connect(self.hide_and_clear)
        status_layout.addWidget(self.close_button)
        self.layout.addLayout(status_layout)

        self.setWidget(self.widget)
        self.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        self.setVisible(False)

        self.matches = []
        self.current_match_index = -1
        self.search_format = QTextCharFormat()
        self.current_match_format = QTextCharFormat()
        self.set_highlight_colors("dark")

        self.parent().tabs.currentChanged.connect(self.on_tab_changed)
        self.search_box.textChanged.connect(self.on_search_box_changed)

        self.escape_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self.escape_shortcut.activated.connect(self.hide_and_clear)

    def set_highlight_colors(self, mode):
        """Sets highlight colors based on the current theme."""
        if mode == "dark":
            self.search_format.setBackground(QColor("#4A4A00"))
            self.current_match_format.setBackground(QColor("#FFA500"))
        else:
            self.search_format.setBackground(QColor("#FFFF00"))
            self.current_match_format.setBackground(QColor("#FF8C00"))

        self.update_match_highlights()

    def on_tab_changed(self):
        """Resets search and highlights when the active tab changes."""
        self.clear_highlights()
        self.matches = []
        self.current_match_index = -1
        self.match_count_label.setText("No matches")
        if self.search_box.text():
            self.find_all_matches(self.search_box.text())

    def on_search_box_changed(self):
        """Triggered when search box text changes, re-finds all matches."""
        self.find_all_matches(self.search_box.text())

    def get_current_editor(self):
        """Helper to get the QTextEdit of the currently active tab."""
        current_tab = self.parent().tabs.currentWidget()
        if current_tab and hasattr(current_tab, 'editor'):
            return current_tab.editor
        return None

    def clear_highlights(self):
        """Clears all search highlights from the editor using setExtraSelections."""
        editor = self.get_current_editor()
        if not editor: return
        editor.setExtraSelections([])

    def update_match_highlights(self):
        """Applies highlights to all found matches and highlights the current match using setExtraSelections."""
        editor = self.get_current_editor()
        if not editor: return

        extra_selections = []
        for i, match_cursor_template in enumerate(self.matches):
            selection = QTextEdit.ExtraSelection()
            selection.cursor = match_cursor_template

            if i == self.current_match_index:
                selection.format = self.current_match_format
            else:
                selection.format = self.search_format
            extra_selections.append(selection)

        editor.setExtraSelections(extra_selections)

    def find_all_matches(self, text):
        """Finds all occurrences of the text and stores their cursors."""
        self.matches = []
        editor = self.get_current_editor()
        if not editor or not text:
            self.match_count_label.setText("No matches")
            self.current_match_index = -1
            self.clear_highlights()
            return

        document = editor.document()
        cursor = QTextCursor(document)
        cursor.movePosition(QTextCursor.Start)

        temp_editor = QTextEdit()
        temp_editor.setDocument(document)
        temp_cursor = temp_editor.textCursor()
        temp_cursor.movePosition(QTextCursor.Start)
        temp_editor.setTextCursor(temp_cursor)

        while True:
            found = temp_editor.find(text, QTextDocument.FindFlags())
            if found:
                self.matches.append(temp_editor.textCursor())
            else:
                break

        if not self.matches:
            self.match_count_label.setText("No matches")
            self.current_match_index = -1
            self.clear_highlights()
        else:
            self.current_match_index = 0
            self.update_match_highlights()
            self.match_count_label.setText(f"{self.current_match_index + 1} of {len(self.matches)}")
            editor.setTextCursor(self.matches[self.current_match_index])
            editor.ensureCursorVisible()

    def find_next(self):
        """Finds the next occurrence of the search term."""
        editor = self.get_current_editor()
        text = self.search_box.text()

        if not editor or not text:
            self.match_count_label.setText("No matches")
            return

        if not self.matches:
            self.find_all_matches(text)
            if not self.matches: return

        self.current_match_index = (self.current_match_index + 1) % len(self.matches)
        editor.setTextCursor(self.matches[self.current_match_index])
        editor.ensureCursorVisible()
        self.match_count_label.setText(f"{self.current_match_index + 1} of {len(self.matches)}")
        self.update_match_highlights()

    def find_prev(self):
        """Finds the previous occurrence of the search term."""
        editor = self.get_current_editor()
        text = self.search_box.text()

        if not editor or not text:
            self.match_count_label.setText("No matches")
            return

        if not self.matches:
            self.find_all_matches(text)
            if not self.matches: return

        self.current_match_index = (self.current_match_index - 1 + len(self.matches)) % len(self.matches)
        editor.setTextCursor(self.matches[self.current_match_index])
        editor.ensureCursorVisible()
        self.match_count_label.setText(f"{self.current_match_index + 1} of {len(self.matches)}")
        self.update_match_highlights()

    def replace_current(self):
        """Replaces the currently highlighted match."""
        editor = self.get_current_editor()
        if not editor or not self.matches or self.current_match_index == -1:
            return

        replace_text = self.replace_box.text()
        current_cursor_template = self.matches[self.current_match_index]

        editor.blockSignals(True)
        replace_cursor = QTextCursor(editor.document())
        replace_cursor.setPosition(current_cursor_template.selectionStart())
        replace_cursor.setPosition(current_cursor_template.selectionEnd(), QTextCursor.KeepAnchor)

        editor.setTextCursor(replace_cursor)
        editor.insertPlainText(replace_text)
        editor.blockSignals(False)

        self.find_all_matches(self.search_box.text())
        current_tab = self.parent().tabs.currentWidget()
        if current_tab:
            current_tab.modified = True
            tab_widget = current_tab.parent().parent()
            tab_widget.setTabText(tab_widget.indexOf(current_tab),
                                  os.path.basename(
                                      current_tab.filename) + " *" if current_tab.filename else "Untitled *")

        if self.matches:
            self.find_next()

    def replace_all(self):
        """Replaces all occurrences of the search term."""
        editor = self.get_current_editor()
        search_text = self.search_box.text()
        replace_text = self.replace_box.text()

        if not editor or not search_text:
            return

        document = editor.document()

        temp_editor_for_finding = QTextEdit()
        temp_editor_for_finding.setDocument(document)

        ranges_to_replace = []
        temp_cursor = temp_editor_for_finding.textCursor()
        temp_cursor.movePosition(QTextCursor.Start)
        temp_editor_for_finding.setTextCursor(temp_cursor)

        while True:
            found = temp_editor_for_finding.find(search_text, QTextDocument.FindFlags())
            if found:
                ranges_to_replace.append((temp_editor_for_finding.textCursor().selectionStart(),
                                          temp_editor_for_finding.textCursor().selectionEnd()))
            else:
                break

        ranges_to_replace.sort(key=lambda x: x[0], reverse=True)

        editor.beginUndoGroup()
        editor.blockSignals(True)
        for start, end in ranges_to_replace:
            cursor = QTextCursor(document)
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            editor.setTextCursor(cursor)
            editor.insertPlainText(replace_text)
        editor.blockSignals(False)
        editor.endUndoGroup()

        current_tab = self.parent().tabs.currentWidget()
        if current_tab:
            current_tab.modified = True
            tab_widget = current_tab.parent().parent()
            tab_widget.setTabText(tab_widget.indexOf(current_tab), os.path.basename(current_tab.filename) + " *" if current_tab.filename else "Untitled *")
        self.find_all_matches(search_text)

    def hide_and_clear(self):
        """Hides the search panel and clears all highlights."""
        self.hide()
        self.clear_highlights()
        self.search_box.clear()
        self.matches = []
        self.current_match_index = -1
        self.match_count_label.setText("No matches")


class MainWindow(QMainWindow):
    """
    The main application window for the JSON Viewer & Editor IDE.
    Manages tabs, menus, toolbars, and application settings.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("JSON Wombat")
        self.setGeometry(100, 100, 1200, 800)
        self.setWindowIcon(QIcon("icons/json_logo.png"))

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.setCentralWidget(self.tabs)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.settings = QSettings("TechJosha-Jones", "JSON Wombat")
        self.load_settings()

        self.search_panel = SearchPanel(self)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.search_panel)

        self.create_actions()

        self.init_menu()
        self.init_toolbar()

        self.set_theme(self.settings.value("theme", "dark"))

        self.load_recent_files()

    def create_actions(self):
        """Creates all QActions for menus and toolbars."""
        self.actions = {}

        self.actions['new'] = QAction("New", self)
        self.actions['new'].setShortcut(QKeySequence.New)
        self.actions['new'].triggered.connect(self.new_tab)

        self.actions['open'] = QAction("Open...", self)
        self.actions['open'].setShortcut(QKeySequence.Open)
        self.actions['open'].triggered.connect(lambda: self.open_file())

        self.actions['save'] = QAction("Save", self)
        self.actions['save'].setShortcut("Ctrl+S")
        self.actions['save'].triggered.connect(self.save_current_tab)

        self.actions['save_as'] = QAction("Save As...", self)
        self.actions['save_as'].setShortcut(QKeySequence.SaveAs)
        self.actions['save_as'].triggered.connect(self.save_as_current_tab)

        self.actions['close_tab'] = QAction("Close Tab", self)
        self.actions['close_tab'].setShortcut(QKeySequence.Close)
        self.actions['close_tab'].triggered.connect(lambda: self.close_tab(self.tabs.currentIndex()))

        self.actions['exit'] = QAction("Exit", self)
        self.actions['exit'].setShortcut(QKeySequence.Quit)
        self.actions['exit'].triggered.connect(self.close)

        # Edit Actions
        self.actions['undo'] = QAction("Undo", self)
        self.actions['undo'].setShortcut(QKeySequence.Undo)
        self.actions['undo'].triggered.connect(self.perform_undo)

        self.actions['redo'] = QAction("Redo", self)
        self.actions['redo'].setShortcut(QKeySequence.Redo)
        self.actions['redo'].triggered.connect(self.perform_redo)

        self.actions['find'] = QAction("Find/Replace...", self)
        self.actions['find'].setShortcut(QKeySequence.Find)
        self.actions['find'].triggered.connect(lambda: self.search_panel.show())

        self.actions['pretty_print'] = QAction("Pretty Print JSON", self)
        self.actions['pretty_print'].triggered.connect(self.pretty_print_current_tab)

        self.actions['minify'] = QAction("Minify JSON", self)
        self.actions['minify'].triggered.connect(self.minify_current_tab)

        self.actions['about'] = QAction("About", self)
        self.actions['about'].triggered.connect(self.show_about_dialog)

    def load_settings(self):
        """Loads application settings from QSettings."""
        self.last_dir = os.path.expanduser("~")
        if not os.path.isdir(self.settings.value("last_dir", "")):
            self.last_dir = os.path.expanduser("~")
        else:
            self.last_dir = self.settings.value("last_dir", os.path.expanduser("~"))

    def save_settings(self):
        """Saves current application settings to QSettings."""
        self.settings.setValue("theme", self.current_theme)
        self.settings.setValue("last_dir", self.last_dir)

        open_files = []
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if tab.filename and os.path.exists(
                    tab.filename):
                open_files.append(tab.filename)
        self.settings.setValue("open_files", open_files)

    def closeEvent(self, event):
        """
        Handles the application close event. Prompts to save unsaved changes
        and saves application settings.
        """
        for i in range(self.tabs.count() - 1, -1, -1):
            tab = self.tabs.widget(i)
            if tab.modified:
                reply = QMessageBox.question(
                    self, "Save Changes?",
                    f"The file '{os.path.basename(tab.filename) if tab.filename else 'Untitled'}' has unsaved changes. Save before closing?",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
                )
                if reply == QMessageBox.Yes:
                    if not tab.save():
                        event.ignore()
                        return
                elif reply == QMessageBox.Cancel:
                    event.ignore()
                    return
            self.tabs.removeTab(i)

        self.save_settings()
        event.accept()

    def load_recent_files(self):
        """Loads previously open files from settings and opens them."""
        open_files = self.settings.value("open_files", [])
        if open_files:
            for fname in open_files:
                if os.path.exists(fname):
                    self.open_file(fname)

    def init_menu(self):
        """Initializes the application's menu bar using common actions."""
        menubar = self.menuBar()

        # File Menu
        file_menu = menubar.addMenu("File")
        file_menu.addAction(self.actions['new'])
        file_menu.addAction(self.actions['open'])
        file_menu.addSeparator()
        file_menu.addAction(self.actions['save'])
        file_menu.addAction(self.actions['save_as'])
        file_menu.addSeparator()
        file_menu.addAction(self.actions['close_tab'])
        file_menu.addAction(self.actions['exit'])

        # Edit Menu
        edit_menu = menubar.addMenu("Edit")
        edit_menu.addAction(self.actions['undo'])
        edit_menu.addAction(self.actions['redo'])
        edit_menu.addSeparator()
        edit_menu.addAction(self.actions['find'])
        edit_menu.addSeparator()
        edit_menu.addAction(self.actions['pretty_print'])
        edit_menu.addAction(self.actions['minify'])

        # View Menu
        view_menu = menubar.addMenu("View")
        theme_menu = view_menu.addMenu("Theme")

        light_action = QAction("Light", self)
        dark_action = QAction("Dark", self)
        light_action.triggered.connect(lambda: self.set_theme("light"))
        dark_action.triggered.connect(lambda: self.set_theme("dark"))
        theme_menu.addAction(light_action)
        theme_menu.addAction(dark_action)

        # Help Menu
        help_menu = menubar.addMenu("Help")
        help_menu.addAction(self.actions['about'])

    def init_toolbar(self):
        """Initializes the application's toolbar using common actions."""
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)

        toolbar.addAction(self.actions['new'])
        toolbar.addAction(self.actions['open'])
        toolbar.addAction(self.actions['save'])
        toolbar.addSeparator()
        toolbar.addAction(self.actions['undo'])
        toolbar.addAction(self.actions['redo'])
        toolbar.addSeparator()
        toolbar.addAction(self.actions['pretty_print'])

    def perform_undo(self):
        """Performs undo action on the current editor, and refreshes highlights."""
        current_tab = self.tabs.currentWidget()
        if current_tab and hasattr(current_tab, 'editor'):
            current_tab.editor.undo()
            if self.search_panel.search_box.text():
                self.search_panel.find_all_matches(self.search_panel.search_box.text())
            else:
                self.search_panel.clear_highlights()

    def perform_redo(self):
        """Performs redo action on the current editor, and refreshes highlights."""
        current_tab = self.tabs.currentWidget()
        if current_tab and hasattr(current_tab, 'editor'):
            current_tab.editor.redo()
            if self.search_panel.search_box.text():
                self.search_panel.find_all_matches(self.search_panel.search_box.text())
            else:
                self.search_panel.clear_highlights()

    def set_theme(self, mode):
        """
        Sets the application-wide theme (light or dark).
        Applies theme to all existing tabs' highlighters.
        """
        self.current_theme = mode
        if mode == "dark":
            QApplication.setStyle(QStyleFactory.create("Fusion"))
            dark_palette = QApplication.palette()
            dark_palette.setColor(QPalette.Window, QColor(53, 53, 53))
            dark_palette.setColor(QPalette.WindowText, Qt.white)
            dark_palette.setColor(QPalette.Base, QColor(25, 25, 25))
            dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
            dark_palette.setColor(QPalette.ToolTipBase, Qt.white)
            dark_palette.setColor(QPalette.ToolTipText, Qt.white)
            dark_palette.setColor(QPalette.Text, Qt.white)
            dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
            dark_palette.setColor(QPalette.ButtonText, Qt.white)
            dark_palette.setColor(QPalette.BrightText, Qt.red)
            dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
            dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
            dark_palette.setColor(QPalette.HighlightedText, Qt.black)
            QApplication.setPalette(dark_palette)
        else:
            QApplication.setStyle(QStyleFactory.create("Fusion"))
            QApplication.setPalette(QApplication.style().standardPalette())

        for i in range(self.tabs.count()):
            tab_widget = self.tabs.widget(i)
            if hasattr(tab_widget, 'highlighter'):
                tab_widget.editor.blockSignals(True)
                tab_widget.highlighter.set_theme(mode)
                tab_widget.editor.blockSignals(False)
        self.search_panel.set_highlight_colors(mode)

    def new_tab(self):
        """Creates and opens a new, empty JSON tab."""
        tab = JsonTab()
        self.tabs.addTab(tab, "Untitled")
        self.tabs.setCurrentWidget(tab)
        if hasattr(tab, 'highlighter'):
            tab.editor.blockSignals(True)
            tab.highlighter.rehighlight()
            tab.editor.blockSignals(False)

    def open_file(self, fname=None):
        """
        Opens a JSON file in a new tab.
        If fname is None, a file dialog is shown.
        """
        if not fname:
            fname, _ = QFileDialog.getOpenFileName(self, "Open JSON", self.last_dir, "JSON Files (*.json)")
        if fname:
            self.last_dir = os.path.dirname(fname)
            try:
                for i in range(self.tabs.count()):
                    tab = self.tabs.widget(i)
                    if tab.filename == fname:
                        self.tabs.setCurrentWidget(tab)
                        self.status_bar.showMessage(f"File '{os.path.basename(fname)}' is already open.", 3000)
                        return

                with open(fname, 'r') as f:
                    content = f.read()
                    tab = JsonTab(fname, content)
                    self.tabs.addTab(tab, os.path.basename(fname))
                    self.tabs.setCurrentWidget(tab)
                    if hasattr(tab, 'highlighter'):
                        tab.editor.blockSignals(True)
                        tab.highlighter.rehighlight()
                        tab.editor.blockSignals(False)
                    self.status_bar.showMessage(f"Opened '{os.path.basename(fname)}'.", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not open file: {e}")
                self.status_bar.showMessage(f"Error opening '{os.path.basename(fname)}'.", 3000)

    def save_current_tab(self):
        """Saves the content of the currently active tab."""
        current = self.tabs.currentWidget()
        if current:
            if current.save():
                self.status_bar.showMessage(f"File '{os.path.basename(current.filename)}' saved successfully.", 3000)

    def save_as_current_tab(self):
        """Saves the content of the currently active tab to a new file."""
        current = self.tabs.currentWidget()
        if current:
            if current.save_as():
                self.status_bar.showMessage(f"File '{os.path.basename(current.filename)}' saved successfully.", 3000)

    def pretty_print_current_tab(self):
        """Pretty prints the JSON in the current tab."""
        current = self.tabs.currentWidget()
        if current:
            current.pretty_print()

    def minify_current_tab(self):
        """Minifies the JSON in the current tab."""
        current = self.tabs.currentWidget()
        if current:
            current.minify()

    def close_tab(self, index):
        """
        Closes a tab at the given index, prompting to save if modified.
        """
        tab = self.tabs.widget(index)
        if not tab:
            return
        if tab.modified:
            reply = QMessageBox.question(
                self, "Save Changes?",
                f"The file '{os.path.basename(tab.filename) if tab.filename else 'Untitled'}' has unsaved changes. Save before closing?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            if reply == QMessageBox.Yes:
                if not tab.save():
                    return
            elif reply == QMessageBox.Cancel:
                return
        self.tabs.removeTab(index)

    def show_about_dialog(self):
        """Displays the 'About' dialog."""
        msg = QMessageBox(self)
        msg.setWindowTitle("About JSON Wombat")
        msg.setTextFormat(Qt.RichText)
        logo_pixmap = QPixmap("icons/json_logo.png")
        if not logo_pixmap.isNull():
            desired_size = QSize(64, 64)
            scaled_pixmap = logo_pixmap.scaled(desired_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            msg.setIconPixmap(scaled_pixmap)
        else:
            print("Error: Logo Fail")
        msg.setText("<b>JSON Wombat</b> Version 0.1 <br>"
                    "A simple yet powerful IDE for viewing and editing JSON files.<br>"
                    "Features:"
                    "<ul>"
                    "<li>Multi-tabbed interface</li>"
                    "<li>Syntax Highlighting</li>"
                    "<li>Pretty Printing & Minifying</li>"
                    "<li>JSON Tree View with navigation</li>"
                    "<li>Dockable Find/Replace Functionality</li>"
                    "<li>Undo/Redo</li>"
                    "<li>Light and Dark Themes</li>"
                    "<li>Session Management (saves open files and theme)</li>"
                    "<li>Status Bar for messages</li>"
                    "</ul>"
                    "<br>"
                    "Developed by:<br>"
                    "<b>Jones Peter</b>: <a href=\"https://jonespeter.site\">jonespeter.site</a><br>"
                    "<b>GitHub</b>: <a href=\"https://github.com/jones-peter\">jones-peter</a>")

        msg.exec_()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setApplicationName("JSON Wombat")
    app.setOrganizationName("TechJosha-Jones")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
