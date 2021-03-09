import requests
import asyncio
import os

import boto3
from botocore.exceptions import ClientError

from mcstatus import MinecraftServer

import discord
from discord.ext import commands
from discord.utils import get

INSTANCE_ID = None # Replace with AWS EC2 instance ID if available
BOT_CHANNEL_ID = 0 # Replace with bot channel ID if available
BOT_TOKEN = "" # Replace with the Discord bot token

# Creates the client to interact with the AWS instance
ec2 = boto3.client('ec2')

# This code automatically gets the instance ID of the first listed instance if one was not provided.
# All caps is technically supposed to represent a constant and we are changing it here which probably isn't
# the greatest practice, but aside from this line it does effectively act as a constant so it's probably okay.
if not INSTANCE_ID:
    instances = ec2.describe_instances()
    INSTANCE_ID = instances["Reservations"][0]["Instances"][0]["InstanceId"]

# The main class that will be used by the Discord bot to interact with the AWS instance and MC server
class InstanceManager:

    # These values are return codes given by the AWS API that show the status of the instance.
    PENDING = 0
    RUNNING = 16
    SHUTTING_DOWN = 32
    TERMINATED = 48
    STOPPING = 64
    STOPPED = 80

    def __init__(self, instance_id: str):
        self.instance_id = instance_id
        self.server = None

    def get_ip(self):
        try:
            # If the IP is available, this API call will have it in the response. If not, a KeyError will be thrown.
            # So by catching that error we can then return None, showing that there was no IP since the server was not running.
            return ec2.describe_instances(InstanceIds=[self.instance_id])['Reservations'][0]['Instances'][0]["PublicIpAddress"]
        except KeyError:
            return None

    def alter_instance(self, turn_on: bool):
        # I think this is technically bad practice (well really most of this bot is), because it is using synchronous
        # networking inside an asynchronous application (discord.py is asynchronous), so it is prone to blocking calls.
        # It's just easier here since we don't need to do any low-level API stuff.
        # If you want to learn more about that do a bit of research on asynchronous structuring in Python, it should explain itself.

        # Anyways a few things happen here. First, we get the function we want to use, since the ec2 object has two different
        # functions for stopping and starting the instance. In Python, you can assign functions to variables, so here I am
        # essentially saying "if we are turning the instance on, use the start_instances function, and if we are turning it off,
        # use the stop_instances function"
        function = ec2.start_instances if turn_on else ec2.stop_instances

        # This next bit is a dry run. You can see that the variable DryRun as specified as true when we call the function that
        # we assigned in the above statement. If DryRun is true, the API will not actually do anything, and will only verify
        # that we can properly execute the command we are trying to execute.
        try:
            function(InstanceIds=[self.instance_id], DryRun=True)
        except ClientError as e:
            # Even if the dry run is successful, it will raised an error because it is a dry run. We can filter out those false errors
            # by basically saying "if DryRunOperation is not in the error message, then we should actually pay attention to the error",
            # and the error is saved to a text file and the function is returned so we don't do any damage when we don't do the dry run.
            if 'DryRunOperation' not in str(e):
                print("Dry run failed, dumping exception to log.txt...")
                with open("log.txt", "w") as f:
                    f.write(str(e))
                return

        # This next bit is basically the exact same thing, except this time DryRun is set to false. Since we already checked that we can
        # do everything okay with the dry run, this shouldn't raised any errors, but still catch them and save them to a file just in case.
        try:
            function(InstanceIds=[self.instance_id], DryRun=False)
        except ClientError as e:
            print("Failed to alter instance, dumping exception to log.txt...")
            with open("log.txt", "w") as f:
                f.write(str(e))
            return

    def get_state(self):
        # Just a simple API call that gets the state code of the instance (listed above)
        return ec2.describe_instances(InstanceIds=[self.instance_id])['Reservations'][0]['Instances'][0]['State']['Code']

    def get_state_str(self):
        # Basically the same as get_state, except it turns it into a string
        state = self.get_state()
        if state == self.PENDING:
            return "starting up"
        elif state == self.RUNNING:
            return "running"
        # I don't think these next two pairs have any difference we really care about, so just check if state is equal to either one of them.
        elif state in (self.SHUTTING_DOWN, self.STOPPING):
            return "shutting down"
        elif state in (self.STOPPED, self.TERMINATED):
            return "stopped"

    async def update_server(self):
        # This function updates the server variable of the object, which stores the information and methods for the Minecraft server.

        # This is a feature that is relatively new to Python called the walrus operator. Search it up if you're not sure what it means.
        if ip := self.get_ip():
            # If the IP is available for us, try to create a new server and run a status check on the server. If that status check fails
            # (TimeoutError is raised), then the AWS instance is running, but the Minecraft server is not, so the server variable should
            # be set to None.
            try:
                self.server = MinecraftServer(ip, 25565)
                await self.server.async_status() # this causes exceptions all over the place but idk why, doesn't seem to matter too much
            except asyncio.exceptions.TimeoutError:
                self.server = None
        else:
            # The AWS instance is not running, so therefore the Minecraft server is not either. Set the server variable to None.
            self.server = None



# This is just setting up the variables we will be using for the Discord bot.
manager = InstanceManager(INSTANCE_ID) # The AWS instance manager that is defined above to be used in commands
client = commands.Bot(command_prefix="?") # The Discord bot to handle the connection and parse commands

# This asynchronous loop updates the channel topic to reflect who is online.
# Note: This function causes a lot of exceptions. I don't think it directly throws all of them. It seems to be something in manager.update_server()
# that for some reason hangs until after the bot is stopped. There's also an exception thrown regarding sockets but I can't locate the source
# of that one either and I don't think it really matters too much since it is ignored. I will try to figure this out sometime.
async def topic_update_loop():
    await client.wait_until_ready() # Wait until the bot has established its connection
    channel = client.get_channel(BOT_CHANNEL_ID) # This is where the #bot-chat channel object is retrieved using the ID.
    while not client.is_closed():
        # This loop runs until the client closes its connection, i.e. the bot is stopped
        await manager.update_server() # Make sure the server is up to date
        if manager.server: # If the server exists/is not None...
            players = manager.server.query().players.names
            await channel.edit(topic=("No players currently online." if len(players) == 0 else "Players online: " + ", ".join(players)))
        else:
            await channel.edit(topic="The Minecraft server is not currently running.")
        await asyncio.sleep(5) # Wait 5 seconds so we don't spam requests

# All of the stuff below uses the decorators included in discord.py. Search up "discord.py documentation" for more information.
# TL;DR: The function names correspond to the Discord command names. Functions that end in _error handle errors raised by the
# corresponding command. This behavior is all defined in discord.py.

@client.command()
async def ip(ctx):
    try:
        state = manager.get_state()
        if state == InstanceManager.PENDING:
            await ctx.send("Please wait, the server is currently starting up.")
        elif state == InstanceManager.RUNNING:
            await ctx.send("The current server IP is {0}".format(manager.get_ip()))
        else:
            await ctx.send("The server is not currently running.")
    except Exception:
        await ctx.send("Something went wrong retrieving the IP.")
        return

@ip.error
async def ip_error(ctx, error):
    if isinstance(error, commands.BadArgument):
        await ctx.send('This command takes no arguments.')
    else:
        await ctx.send('Something went wrong with the command.')

@client.command()
async def status(ctx):
    await ctx.send("The server is currently {0}.".format(manager.get_state_str()))

@status.error
async def status_error(ctx, error):
    if isinstance(error, commands.BadArgument):
        await ctx.send('This command takes no arguments.')
    else:
        await ctx.send('Something went wrong with the command.')

@client.command()
async def spinup(ctx):
    state = manager.get_state()
    if state == InstanceManager.PENDING:
        await ctx.send("The server is already starting up.")
    elif state == InstanceManager.RUNNING:
        await ctx.send("The server is already running.")
    elif state in (InstanceManager.SHUTTING_DOWN, InstanceManager.STOPPING):
        await ctx.send("Please wait, the server is currently shutting down.")
    elif state in (InstanceManager.STOPPED, InstanceManager.TERMINATED):
        manager.alter_instance(True)
        await ctx.send("The server has been started.")

@spinup.error
async def spinup_error(ctx, error):
    if isinstance(error, commands.BadArgument):
        await ctx.send('This command takes no arguments.')
    else:
        await ctx.send('Something went wrong with the command.')

@client.command()
async def spindown(ctx):
    state = manager.get_state()
    if state == InstanceManager.PENDING:
        await ctx.send("Please wait, the server is currently starting up.")
    elif state in (InstanceManager.SHUTTING_DOWN, InstanceManager.STOPPING):
        await ctx.send("The server is already shutting down.")
    elif state in (InstanceManager.STOPPED, InstanceManager.TERMINATED):
        await ctx.send("The server was already stopped.")
    elif state == InstanceManager.RUNNING:
        manager.alter_instance(False)
        await ctx.send("The server has been stopped.")

@spindown.error
async def spindown_error(ctx, error):
    if isinstance(error, commands.BadArgument):
        await ctx.send('This command takes no arguments.')
    else:
        await ctx.send('Something went wrong with the command.')

# The Discord bot will automatically call this when it has been set up.
@client.event
async def on_ready():
    print('Friendo bot has been set up.')

# This adds the topic_update_loop function from above to the client's asynchronous event loop so it can run
# in the background.
client.loop.create_task(topic_update_loop())

# This is where the Discord bot is finally run. It takes the bot's secret token as a parameter, which should
# never be shared, so I didn't include it here.
client.run(BOT_TOKEN)