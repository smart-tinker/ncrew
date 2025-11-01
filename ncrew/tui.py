"""Textual TUI application for interacting with CLI agents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from textwrap import dedent
from typing import Iterable

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, Static, TextLog

from .coordinator import AgentUnavailableError, Message, SessionCoordinator


@dataclass(slots=True)
class DisplayMessage:
    """Formatted message ready for rendering."""

    speaker: str
    role: str
    timestamp: datetime
    content: str


class HelpScreen(ModalScreen[None]):
    """Simple help overlay with key bindings."""

    def compose(self) -> ComposeResult:
        yield Static(
            dedent(
                """
                ncrew — клавиши управления

                Enter       отправить сообщение всем агентам
                Ctrl+R      перечитать настройки из ~/.ncrew/settings.json
                ?           показать это окно
                Ctrl+C      выйти из приложения
                """
            ),
            id="help",
        )

    def on_mount(self) -> None:
        self.query_one(Static).border_title = "Справка"

    def on_key(self, event) -> None:  # type: ignore[override]
        self.dismiss()


class NcrewApp(App[None]):
    """Main Textual application."""

    CSS = """
    Screen {
        layout: vertical;
    }

    # Layout container with agent list on the left and conversation on the right
    #  ┌─────────────┬──────────────────────────────┐
    #  │ Agents      │ Conversation + input         │
    #  └─────────────┴──────────────────────────────┘

    # Agent list column
    # ------------------
    # Provide a minimum width so that agent names remain readable.
    # The conversation area grows to fill the remaining space.

    # Containers
    .main-container {
        height: 1fr;
    }

    .conversation {
        height: 1fr;
    }

    # Widgets
    # -------
    ListView {
        width: 28;
        border: tall $primary;
    }

    TextLog {
        border: tall $surface;
    }

    # Status widget at the bottom of the main area
    # ---------------------------------------------
    # Keep it compact but allow wrapping for long messages.
    #
    # This area displays validation errors or process failures.
    #
    # History entries use the theme colours and rely on ``TextLog`` wrapping.

    # Input line should stand out from log.
    Input#prompt {
        border: tall $primary;
    }

    Static#status {
        height: auto;
        border: wide $warning;
        padding: 1 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+r", "reload_settings", "Reload settings"),
        Binding("?", "show_help", "Help"),
    ]

    def __init__(self, coordinator: SessionCoordinator) -> None:
        super().__init__()
        self.coordinator = coordinator
        self.status_text: str = coordinator.status_message

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header()
        with Container(classes="main-container"):
            with Horizontal():
                yield ListView(id="agents")
                with Vertical(classes="conversation"):
                    yield TextLog(highlight=False, markup=False, wrap=True, id="history")
                    yield Input(placeholder="Введите сообщение…", id="prompt")
                    yield Static(self.status_text, id="status")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_agents()
        self._render_history()
        self._update_status(self.coordinator.status_message)
        self.query_one(Input).focus()

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------
    def _render_history(self) -> None:
        log = self.query_one(TextLog)
        log.clear()
        for message in self._format_history(self.coordinator.get_history()):
            log.write(self._format_for_display(message))

    def _append_message(self, message: Message) -> None:
        log = self.query_one(TextLog)
        log.write(self._format_for_display(self._format_message(message)))

    def _format_history(self, history: Iterable[Message]) -> Iterable[DisplayMessage]:
        for message in history:
            yield self._format_message(message)

    def _format_message(self, message: Message) -> DisplayMessage:
        role = message.role
        if role == "user":
            speaker = "Вы"
        elif role == "error":
            agent_name = self.coordinator.get_agent_name(message.agent_id) or "неизвестный агент"
            speaker = f"Ошибка ({agent_name})"
        else:
            speaker = self.coordinator.get_agent_name(message.agent_id) or (message.agent_id or "Агент")
        return DisplayMessage(
            speaker=speaker,
            role=role,
            timestamp=message.timestamp,
            content=message.content,
        )

    def _format_for_display(self, formatted: DisplayMessage) -> str:
        timestamp = ""
        if self.coordinator.ui_settings.show_timestamps:
            timestamp = formatted.timestamp.strftime("[%H:%M:%S] ")
        prefix = f"{timestamp}{formatted.speaker}:"
        return f"{prefix}\n{formatted.content}\n"

    def _refresh_agents(self) -> None:
        view = self.query_one(ListView)
        view.clear()
        for agent in self.coordinator.agents:
            item = ListItem(Label(agent.name), id=agent.id)
            view.append(item)
        view.disabled = True

    def _update_status(self, status: str) -> None:
        self.status_text = status
        self.query_one("#status", Static).update(status or "")

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def on_input_submitted(self, event: Input.Submitted) -> None:
        content = event.value.strip()
        if not content:
            return
        event.input.value = ""
        try:
            user_message = self.coordinator.record_user_message(content)
        except AgentUnavailableError as exc:
            self._update_status(str(exc))
            return
        self._append_message(user_message)
        self._update_status("Ожидание ответа…")
        self._invoke_agents_async(content)

    @work(thread=True)
    def _invoke_agents_async(self, content: str) -> None:
        for message in self.coordinator.broadcast_prompt(content):
            status = self.coordinator.status_message
            self.call_from_thread(self._after_agent_message, message, status)

    def _after_agent_message(self, message: Message, status: str) -> None:
        self._append_message(message)
        self._update_status(status)

    def action_reload_settings(self) -> None:
        self.coordinator.reload_settings()
        self._refresh_agents()
        self._render_history()
        self._update_status(self.coordinator.status_message)

    def action_show_help(self) -> None:
        self.push_screen(HelpScreen())

    # ------------------------------------------------------------------
    # Helper utilities
    # ------------------------------------------------------------------
def run_tui(coordinator: SessionCoordinator) -> None:
    """Run the textual application."""

    app = NcrewApp(coordinator)
    app.run()


__all__ = ["NcrewApp", "run_tui"]
