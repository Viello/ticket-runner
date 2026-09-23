"""In-memory test double conforming to DiscordGateway."""

from __future__ import annotations

from typing import Any, NamedTuple


class DiscordCall(NamedTuple):
    """Record of a single invocation on DiscordGateway."""

    method: str
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = {}

    @property
    def channel_or_thread_id(self) -> str | None:
        """Convenience accessor for channel or thread ID."""
        if "channel_or_thread_id" in self.kwargs:
            return self.kwargs["channel_or_thread_id"]
        if "channel_id" in self.kwargs:
            return self.kwargs["channel_id"]
        if "thread_id" in self.kwargs:
            return self.kwargs["thread_id"]
        if len(self.args) > 0:
            return self.args[0]
        return None

    @property
    def channel_id(self) -> str | None:
        """Convenience accessor for parent channel ID."""
        if "channel_id" in self.kwargs:
            return self.kwargs["channel_id"]
        if self.method == "create_thread" and len(self.args) > 0:
            return self.args[0]
        return None

    @property
    def thread_id(self) -> str | None:
        """Convenience accessor for thread ID."""
        if "thread_id" in self.kwargs:
            return self.kwargs["thread_id"]
        if self.method in ("edit_thread", "archive_thread") and len(self.args) > 0:
            return self.args[0]
        return None

    @property
    def message_id(self) -> str | None:
        """Convenience accessor for message ID."""
        if "message_id" in self.kwargs:
            return self.kwargs["message_id"]
        if self.method in ("edit_message", "pin_message", "delete_message") and len(self.args) > 1:
            return self.args[1]
        return None

    @property
    def content(self) -> str | None:
        """Convenience accessor for message content."""
        if "content" in self.kwargs:
            return self.kwargs["content"]
        if self.method == "post_message" and len(self.args) > 1:
            return self.args[1]
        if self.method == "edit_message" and len(self.args) > 2:
            return self.args[2]
        return None

    @property
    def embed(self) -> dict[str, Any] | None:
        """Convenience accessor for embed payload."""
        return self.kwargs.get("embed")

    @property
    def name(self) -> str | None:
        """Convenience accessor for thread name."""
        if "name" in self.kwargs:
            return self.kwargs["name"]
        if self.method == "create_thread" and len(self.args) > 1:
            return self.args[1]
        return None

    @property
    def starter_message(self) -> str | None:
        """Convenience accessor for starter message text."""
        if "starter_message" in self.kwargs:
            return self.kwargs["starter_message"]
        if self.method == "create_thread" and len(self.args) > 2:
            return self.args[2]
        return None

    @property
    def archived(self) -> bool | None:
        """Convenience accessor for thread archived flag."""
        return self.kwargs.get("archived")

    @property
    def locked(self) -> bool | None:
        """Convenience accessor for thread locked flag."""
        return self.kwargs.get("locked")


class FakeDiscordGateway:
    """In-memory test double conforming to the DiscordGateway protocol."""

    def __init__(
        self,
        permissions: list[str] | None = None,
        raise_on_get_permissions: Exception | None = None,
        create_thread_return: tuple[str, str] | None = None,
        raise_on_archive_thread: Exception | None = None,
        raise_on_post_message: Exception | None = None,
        raise_on_edit_message: Exception | None = None,
        raise_on_create_thread: Exception | None = None,
    ) -> None:
        self.calls: list[DiscordCall] = []
        self.messages: dict[str, dict[str, Any]] = {}
        self.threads: dict[str, dict[str, Any]] = {}
        self.pinned_messages: list[str] = []
        self.pending_replies: list[str] = []
        self._next_id: int = 1
        self.create_thread_return: tuple[str, str] | None = create_thread_return
        self.raise_on_archive_thread: Exception | None = raise_on_archive_thread
        self.raise_on_post_message: Exception | None = raise_on_post_message
        self.raise_on_edit_message: Exception | None = raise_on_edit_message
        self.raise_on_create_thread: Exception | None = raise_on_create_thread
        self.permissions: list[str] = (
            list(permissions)
            if permissions is not None
            else [
                "Send Messages",
                "Send Messages in Threads",
                "Create Public Threads",
                "Manage Threads",
                "Manage Messages",
                "Read Message History",
                "Embed Links",
            ]
        )
        self.raise_on_get_permissions: Exception | None = raise_on_get_permissions

    def _generate_id(self) -> str:
        new_id = str(self._next_id)
        self._next_id += 1
        return new_id

    async def get_permissions(self, channel_id: str) -> list[str]:
        """Return configured bot permissions for channel."""
        self.calls.append(
            DiscordCall(
                method="get_permissions",
                args=(channel_id,),
                kwargs={},
            )
        )
        if self.raise_on_get_permissions is not None:
            raise self.raise_on_get_permissions
        return list(self.permissions)

    async def post_message(
        self,
        channel_or_thread_id: str,
        content: str,
        *,
        embed: dict[str, Any] | None = None,
    ) -> str:
        """Post message into in-memory store and record call."""
        if self.raise_on_post_message is not None:
            raise self.raise_on_post_message
        msg_id = self._generate_id()
        self.calls.append(
            DiscordCall(
                method="post_message",
                args=(channel_or_thread_id, content),
                kwargs={"embed": embed},
            )
        )
        self.messages[msg_id] = {
            "channel_or_thread_id": channel_or_thread_id,
            "content": content,
            "embed": embed,
            "pinned": False,
        }
        return msg_id

    async def edit_message(
        self,
        channel_or_thread_id: str,
        message_id: str,
        content: str,
        *,
        embed: dict[str, Any] | None = None,
    ) -> None:
        """Edit message in in-memory store and record call."""
        if self.raise_on_edit_message is not None:
            raise self.raise_on_edit_message
        self.calls.append(
            DiscordCall(
                method="edit_message",
                args=(channel_or_thread_id, message_id, content),
                kwargs={"embed": embed},
            )
        )
        msg = self.messages.setdefault(
            message_id,
            {
                "channel_or_thread_id": channel_or_thread_id,
                "pinned": False,
            },
        )
        msg["content"] = content
        msg["embed"] = embed

    async def pin_message(
        self,
        channel_or_thread_id: str,
        message_id: str,
    ) -> None:
        """Pin message in in-memory store and record call."""
        self.calls.append(
            DiscordCall(
                method="pin_message",
                args=(channel_or_thread_id, message_id),
                kwargs={},
            )
        )
        if message_id in self.messages:
            self.messages[message_id]["pinned"] = True
        if message_id not in self.pinned_messages:
            self.pinned_messages.append(message_id)

    async def create_thread(
        self,
        channel_id: str,
        name: str,
        starter_message: str,
        *,
        embed: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        """Create thread and starter message in in-memory store and record call."""
        if self.create_thread_return is not None:
            thread_id, starter_message_id = self.create_thread_return
        else:
            thread_id = self._generate_id()
            starter_message_id = self._generate_id()

        self.calls.append(
            DiscordCall(
                method="create_thread",
                args=(channel_id, name, starter_message),
                kwargs={"embed": embed},
            )
        )
        self.messages[starter_message_id] = {
            "channel_or_thread_id": channel_id,
            "content": starter_message,
            "embed": embed,
            "pinned": False,
        }
        self.threads[thread_id] = {
            "channel_id": channel_id,
            "name": name,
            "starter_message_id": starter_message_id,
            "archived": False,
            "locked": False,
        }
        return (thread_id, starter_message_id)

    async def edit_thread(
        self,
        thread_id: str,
        *,
        archived: bool = False,
        locked: bool = False,
    ) -> None:
        """Update thread archived and locked status and record call."""
        self.calls.append(
            DiscordCall(
                method="edit_thread",
                args=(thread_id,),
                kwargs={"archived": archived, "locked": locked},
            )
        )
        thread = self.threads.setdefault(
            thread_id,
            {
                "channel_id": "",
                "name": "",
                "starter_message_id": "",
            },
        )
        thread["archived"] = archived
        thread["locked"] = locked

    async def archive_thread(
        self,
        thread_id: str,
    ) -> None:
        """Archive and lock thread in in-memory store and record call."""
        self.calls.append(
            DiscordCall(
                method="archive_thread",
                args=(thread_id,),
                kwargs={},
            )
        )
        if self.raise_on_archive_thread is not None:
            raise self.raise_on_archive_thread
        thread = self.threads.setdefault(
            thread_id,
            {
                "channel_id": "",
                "name": "",
                "starter_message_id": "",
            },
        )
        thread["archived"] = True
        thread["locked"] = True

    async def delete_message(
        self,
        channel_or_thread_id: str,
        message_id: str,
    ) -> None:
        """Delete message in in-memory store and record call."""
        self.calls.append(
            DiscordCall(
                method="delete_message",
                args=(channel_or_thread_id, message_id),
                kwargs={},
            )
        )
        self.messages.pop(message_id, None)
        if message_id in self.pinned_messages:
            self.pinned_messages.remove(message_id)

