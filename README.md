# aws-mc-bot

A Discord bot to manage the starting up and shutting down of an AWS instance with a Minecraft server.

There is an obscene number of comments in the file because I want to make it easy to interpret so others can look into it and learn (hopefully my coding practices aren't too bad).

## Installation

First, install the Python requirements using `python -m pip install -r requirements.txt`. This should also install the Boto3 AWS CLI onto your computer, which will allow you to use the `aws` command on your command line.

You can then follow the instructions [here](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/quickstart.html) to get the AWS SDK set up on your computer and link it to your account so it can modify your instances. You should only have to do this step once.

After that, go inside `aws-mc-bot.py` and modify the specifications to your liking. You can get the Discord channel ID by right clicking the channel, and the bot token can be found on the bot configuration page in the Discord developer portal.

You should be able to run `aws-mc-bot.py` now. It might throw a bunch of exceptions, but those can be ignored. I am working on a fix.

## Usage

The Discord bot (prefixed `?`) comes with a few commands:
- `help` - Displays a list of the available commands.
- `ip` - Reveals the public IP of the instance/server if it is running.
- `spindown` - Stops the server/instance.
- `spinup` - Starts the server.
- `status` - Gets the current status of the server.

Commands should be spam-resistant, but still try not to send them too fast just in case.