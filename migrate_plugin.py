"""
Avionico Modmail Migration Plugin
Install: .plugins add eggydedededediaaiai/modmail-migrate/migrate_plugin@main
Usage:   .migrate <token>

Get your token from the Avionico dashboard: Bot Settings -> Data Migration -> Migration Plugin.
"""

import aiohttp
from discord.ext import commands

BASE_URL = "https://modmailapi.avioni.co"
PUSH_URL = f"{BASE_URL}/api/migrate/push"
DONE_URL = f"{BASE_URL}/api/migrate/done"
BATCH_SIZE = 500

# Never push these - they contain credentials or are MongoDB internals
SKIP_COLLECTIONS = {
    "system.indexes", "system.users", "system.profile",
    "system.js", "system.views",
}

# Fields stripped from config - only things tied to the old bot's identity
STRIP_KEYS = {
    "token", "bot_token", "mongo_uri", "mongo_db",
    "database_uri", "database_type", "bot_id", "_id",
}


def sanitize(collection: str, doc: dict) -> dict:
    out = {}
    for k, v in doc.items():
        if k == "_id":
            continue
        if collection == "config":
            if k in STRIP_KEYS:
                continue
            low = k.lower()
            if "mongo" in low or "database_uri" in low:
                continue
        out[k] = v
    return out


class MigratePlugin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="migrate")
    @commands.has_permissions(administrator=True)
    async def migrate_cmd(self, ctx, token: str = None):
        """Push this bot's data to Avionico. Usage: .migrate <token>"""
        if not token:
            await ctx.send(
                "**Avionico Migration**\n"
                "Usage: `.migrate <token>`\n"
                "Get your token from the Avionico dashboard under Data Migration."
            )
            return

        msg = await ctx.send("Scanning collections...")
        db = self.bot.db

        # Discover all collections dynamically
        try:
            all_collections = await db.list_collection_names()
        except Exception as e:
            await msg.edit(content=f"Failed to list collections: {e}")
            return

        collections_to_push = [
            c for c in all_collections
            if c not in SKIP_COLLECTIONS and not c.startswith("system.")
        ]

        if not collections_to_push:
            await msg.edit(content="No collections found to migrate.")
            return

        await msg.edit(content=f"Found {len(collections_to_push)} collections. Migrating...")

        total = 0
        errors = []

        async with aiohttp.ClientSession() as session:
            for col_name in collections_to_push:
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
                        async with session.post(
                            PUSH_URL,
                            json=payload,
                            timeout=aiohttp.ClientTimeout(total=60)
                        ) as resp:
                            if resp.status == 200:
                                total += len(batch)
                            elif resp.status == 401:
                                await msg.edit(content="Token is invalid or expired. Generate a new one from the Avionico dashboard.")
                                return
                            else:
                                text = await resp.text()
                                errors.append(f"{col_name}: {resp.status} {text[:80]}")
                                break
                except Exception as e:
                    errors.append(f"{col_name}: {type(e).__name__}: {e}")

            # Signal done - restarts bot to load new config
            try:
                async with session.post(
                    DONE_URL,
                    json={"token": token},
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    restarted = resp.status == 200
            except Exception:
                restarted = False

        restart_note = (
            " Your bot has been restarted and will load the new config shortly."
            if restarted else
            " Restart the bot from the Avionico dashboard to apply the new config."
        )

        if errors:
            err_lines = "\n".join(errors)
            await msg.edit(
                content=f"Migration finished with some issues. {total} documents pushed.\n```\n{err_lines}\n```{restart_note}"
            )
        else:
            await msg.edit(
                content=f"Done. {total} documents pushed to Avionico across {len(collections_to_push)} collections.{restart_note}"
            )


async def setup(bot):
    await bot.add_cog(MigratePlugin(bot))
