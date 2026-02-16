from __future__ import annotations

import logging

import discord
from discord.ext import commands

from .config import Settings, load_settings


logger = logging.getLogger("discord_codex_gateway")


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def _is_allowed_message(settings: Settings, message: discord.Message) -> bool:
    if message.author.bot:
        return False
    if message.author.id != settings.allowed_user_id:
        return False
    if settings.allowed_channel_id is not None and message.channel.id != settings.allowed_channel_id:
        return False
    return True


def build_bot(settings: Settings) -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

    @bot.event
    async def on_ready() -> None:
        logger.info("Bot online as %s (id=%s)", bot.user, bot.user.id if bot.user else "unknown")

    @bot.event
    async def on_message(message: discord.Message) -> None:
        if not _is_allowed_message(settings, message):
            return
        await bot.process_commands(message)

    @bot.command(name="ping")
    async def ping(ctx: commands.Context[commands.Bot]) -> None:
        await ctx.reply("pong", mention_author=False)

    return bot


def main() -> None:
    _configure_logging()
    settings = load_settings()
    bot = build_bot(settings)
    bot.run(settings.discord_token)


if __name__ == "__main__":
    main()
