"""
avionico Modmail Migration Plugin
----------------------------------
Installs on your old modmail bot and pushes data to avionico Modmail.

Usage:
  {prefix}plugins add eggydedededediaaiai/modmail-migrate/migrate_plugin@main
  {prefix}migrate <token>

The token is generated from the avionico Modmail dashboard (Bot -> Data Migration -> Migration Plugin).
"""

import discord
import motor.motor_asyncio
import aiohttp
from discord.ext import commands

AVIONICO_PUSH_URL = "https://modmailapi.avioni.co/api/migrate/push"
AVIONICO_DONE_URL = "https://modmailapi.avioni.co/api/migrate/done"
COLLECTIONS = ["logs", "config", "plugins", "snippets", "aliases", "blocked"]
BATCH_SIZE = 500


class Migrate(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="migrate")
    @commands.has_permissions(administrator=True)
    async def migrate(self, ctx, token: str = None):
        """Push this bot's data to avionico Modmail. Usage: {prefix}migrate <token>"""
        if not token:
            await ctx.send("Usage: `{prefix}migrate <token>`\nGet your token from the avionico Modmail dashboard -> Bot -> Data Migration -> Migration Plugin.")
            return

        msg = await ctx.send("Starting migration to avionico Modmail...")
        db = self.bot.db

        total = 0
        errors = []
        async with aiohttp.ClientSession() as session:
            for col_name in COLLECTIONS:
                try:
                    collection = db[col_name]
                    cursor = collection.find({})
                    documents = []
                    async for doc in cursor:
                        doc.pop("_id", None)
                        documents.append(doc)

                    if not documents:
                        continue

                    # Push in batches
                    for i in range(0, len(documents), BATCH_SIZE):
                        batch = documents[i:i + BATCH_SIZE]
                        payload = {
                            "token": token,
                            "collection": col_name,
                            "documents": batch,
                        }
                        async with session.post(AVIONICO_PUSH_URL, json=payload) as resp:
                            if resp.status == 200:
                                total += len(batch)
                            elif resp.status == 401:
                                await msg.edit(content="Invalid or expired token. Generate a new one from the avionico Modmail dashboard.")
                                return
                            else:
                                text = await resp.text()
                                errors.append(f"{col_name}: {resp.status} {text[:100]}")
                except Exception as e:
                    errors.append(f"{col_name}: {e}")

        # Signal done so the new bot restarts and picks up the imported data
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(AVIONICO_DONE_URL, json={"token": token})
        except Exception:
            pass

        if errors:
            err_text = "\n".join(errors)
            await msg.edit(content=f"Migration finished with errors. {total} documents sent.\n```\n{err_text}\n```")
        else:
            await msg.edit(content=f"Migration complete. {total} documents pushed to avionico Modmail successfully. Your new bot is restarting to apply the data.")


async def setup(bot):
    await bot.add_cog(Migrate(bot))
