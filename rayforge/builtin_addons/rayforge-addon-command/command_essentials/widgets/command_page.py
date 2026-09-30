"""Command step settings page: a multi-line machine-code editor."""

from gettext import gettext as _
from typing import Any

from gi.repository import Adw, Gtk

from rayforge.ui_gtk.doceditor.step_settings.pages.base import (
    StepSettingsPage,
)


class CommandStepSettingsPage(StepSettingsPage):
    """Settings page for the CommandStep.

    A single monospace text editor for the machine-code lines. The
    text is stored unexpanded; path variables like ``{machine.name}``
    and ``{layer.name}`` are resolved when the job is encoded.
    """

    def __init__(self, editor: Any, step: Any):
        super().__init__(editor, step)
        self._add_step_sections()

    def _add_step_sections(self):
        self._text_view = Gtk.TextView()
        self._text_view.set_wrap_mode(Gtk.WrapMode.NONE)
        self._text_view.set_monospace(True)
        buffer = self._text_view.get_buffer()
        buffer.set_text(self.step.command_text)
        buffer.connect("changed", self._on_buffer_changed)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_size_request(-1, 220)
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_child(self._text_view)

        row = Adw.ActionRow()
        row.set_activatable(False)
        row.add_css_class("property")
        row.set_child(scrolled)

        self.add_section(
            _("Machine Code"),
            row,
            description=_(
                "One line per command, emitted at this step's "
                "position in the workflow. Path variables like "
                "{machine.name} and {layer.name} are expanded when "
                "the job is encoded."
            ),
        )

    def _on_buffer_changed(self, buffer: Gtk.TextBuffer):
        text = buffer.get_text(
            buffer.get_start_iter(), buffer.get_end_iter(), False
        )
        self._debounce(self._commit_text, text)

    def _commit_text(self, text: str):
        if text != self.step.command_text:
            self.set_step_property("command_text", text)

    def _sync_widgets_to_model(self, *_args):
        super()._sync_widgets_to_model(*_args)
        buffer = self._text_view.get_buffer()
        current = buffer.get_text(
            buffer.get_start_iter(), buffer.get_end_iter(), False
        )
        if current != self.step.command_text:
            buffer.set_text(self.step.command_text)
