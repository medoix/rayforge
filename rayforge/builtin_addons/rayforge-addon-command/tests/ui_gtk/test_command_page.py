# flake8: noqa: E402
"""UI tests for the Command step settings page."""

import gi
import pytest

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from command_essentials.steps import CommandStep
from command_essentials.widgets.command_page import CommandStepSettingsPage
from gi.repository import Adw

from rayforge.ui_gtk.doceditor.step_settings.pages import StepSettingsPage


def _buffer_text(page) -> str:
    buffer = page._text_view.get_buffer()
    return buffer.get_text(
        buffer.get_start_iter(), buffer.get_end_iter(), False
    )


@pytest.mark.ui
def test_command_page_shows_text(editor, machine):
    step = CommandStep.create(editor.context)
    step.command_text = "M101\nG4 P2"

    page = CommandStepSettingsPage(editor, step)

    assert isinstance(page, StepSettingsPage)
    assert isinstance(page, Adw.PreferencesPage)
    assert _buffer_text(page) == "M101\nG4 P2"


@pytest.mark.ui
def test_command_page_edit_updates_step(editor, machine):
    step = CommandStep.create(editor.context)
    page = CommandStepSettingsPage(editor, step)

    buffer = page._text_view.get_buffer()
    buffer.set_text("M103")
    page._commit_text("M103")

    assert step.command_text == "M103"


@pytest.mark.ui
def test_command_page_model_sync_overrides_buffer(editor, machine):
    step = CommandStep.create(editor.context)
    page = CommandStepSettingsPage(editor, step)

    step.set_command_text("M104")

    assert _buffer_text(page) == "M104"
