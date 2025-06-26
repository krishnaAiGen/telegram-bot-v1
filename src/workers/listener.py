import asyncio
from telethon import events



async def listener_handler(event: events.NewMessage.Event, brain_queue: asyncio.Queue):
    await brain_queue.put(event.message)