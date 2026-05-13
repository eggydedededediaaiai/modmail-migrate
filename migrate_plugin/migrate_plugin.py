"""
avionico Modmail Migration Plugin
Install: .plugins add eggydedededediaaiai/modmail-migrate@main
Usage:   .migrate <token>

Get your token from the avionico Modmail dashboard: Bot Settings -> Data Migration -> Migration Plugin.
"""

import aiohttp
from discord.ext import commands

PUSH_URL = "https://modmailapi.avioni.co/api/migrate/push"
COLLECTIONS = ["logs", "config", "plugins", "snippets", "aliases", "blocked"]
BATCH_SIZE = 500

# Fields that belong to the old bot and must never be sent
STRIP_KEYS = {
    "token", "bot_token", "mongo_uri", "mongo_db", "database_uri",
    "database_type", "bot_id", "guild_id", "owners", "_id",
    "prefix", "log_channel_id",
}


def sanitize(collection: str, doc: dict) -> dict:
    out = {}
    for k, v in doc.items():
        if collection == "config":
            low = k.lower()
            if k in STRIP_KEYS:
                continue
            if any(word in low for word in ("token", "secret", "uri", "password")):
                continue
        else:
            if k == "_id":
                continue
        out[k] = v
    return out


class Migrate(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="migrate")
    @commands.has_permissions(administrator=True)
    async def migrate_cmd(self, ctx, token: str = None):
        """Push this bot's data to Avionico. Usage: .migrate <token>"""
        if not token:
            await ctx.send(
                "**avionico Migration**\n"
                "Usage: `.migrate <token>`\n"
                "Get your token from the avionico Modmail dashboard -> Bot Settings -> Data Migration -> Migration Plugin."
            )
            return

        msg = await ctx.send("Starting migration, please wait...")
        db = self.bot.db
        total = 0
        errors = []

        async with aiohttp.ClientSession() as session:
            for col_name in COLLECTIONS:
                try:
                    collection = db[col_name]
                    raw_docs = await collection.find({}).to_list(length=None)
                    if not raw_docs:
                        continue

                    docs = [sanitize(col_name, dict(d)) for d in raw_docs]

                    for i in range(0, len(docs), BATCH_SIZE):
                        batch = docs[i:i + BATCH_SIZE]
                        payload = {
                            "token": token,
                            "collection": col_name,
                            "documents": batch,
                        }
                        async with session.post(PUSH_URL, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                            if resp.status == 200:
                                total += len(batch)
                            elif resp.status == 401:
                                await msg.edit(content="Token is invalid or expired. Generate a new one from the avionico Modmail dashboard.")
                                return
                            else:
                                text = await resp.text()
                                errors.append(f"{col_name}: server returned {resp.status}")
                                break
                except Exception as e:
                    errors.append(f"{col_name}: {type(e).__name__}")

        if errors:
            err_lines = "\n".join(errors)
            await msg.edit(content=f"Migration finished with some issues. {total} documents pushed.\n```\n{err_lines}\n```")
        else:
            await msg.edit(content=f"Done. {total} documents pushed to avionico Modmail successfully.")


async def setup(bot):
    await bot.add_cog(Migrate(bot))
