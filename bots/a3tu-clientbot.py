#!/usr/bin/python3

#from discord import User
#from discord.ext.commands import Bot
import discord
import subprocess
import os
import re
import fileinput
import time
import aiohttp
import asyncio
import json
#from discord.ext import commands
#from contextlib import closing

def modPaths(modList):
    longModPaths = []
    shortModPaths = []
    for eachDir in modList:
        for mod in os.listdir('/home/steam/arma3/a3tu/mods/' + eachDir):
            if re.search('^\.',mod):
                continue
            longModPaths = longModPaths + ["mods/" + eachDir + "/" + mod]
            shortModPaths = shortModPaths + [mod]

    sortShort = {}
    sortLong = {}

    for item in shortModPaths:
        if re.search('@cba_a3$',item):
            sortShort["@cba_a3"] = 1
        elif re.search('@ace$',item):
            sortShort["@ace"] = 2
        else:
            sortShort[item] = 3

    for item in longModPaths:
        if re.search('@cba_a3$',item):
            sortLong["mods/tempunitbaserepo/@cba_a3"] = 1
        elif re.search('@ace$',item):
            sortLong["mods/tempunitbaserepo/@ace"] = 2
        else:
            sortLong[item] = 3

    shortModPaths = [(k) for k in sorted(sortShort, key=sortShort.get)]
    # shortModPaths = [(k, sortShort[k]) for k in sorted(sortShort, key=sortShort.get)]
    longModPaths = [(k) for k in sorted(sortLong, key=sortLong.get)]
    # longModPaths = [(k, sortLong[k]) for k in sorted(sortLong, key=sortLong.get)]

    #for key in shortModPaths:
    #    print(key)
    #for key in longModPaths:
    #    print(key)

    return longModPaths,shortModPaths


def writeFile(filename,allModPaths):
    myfile = fileinput.FileInput(filename, inplace=True)

    newMods = 'mod=\"-mod='
    newServerMods = 'serverMod=\"-serverMod='
    for m in allModPaths:
        newMods = newMods + m + ";"
        newServerMods = newServerMods + m + ";"
    newMods = newMods + '"'
    newServerMods = newServerMods + '"'

    for line in myfile:
        line = re.sub(r"mod=\"-mod.*\"",
                      newMods,
                      line.rstrip())
        line = re.sub(r"serverMod=\"-serverMod.*\"",
                      newServerMods,
                      line.rstrip())
        print(line)


def get_command(script_commands_json, cmd):
    with open(script_commands_json, 'r') as f:
        script_commands = json.load(f)
    return script_commands[cmd]


async def run(cmd):
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)

    stdout, stderr = await proc.communicate()

    #print(f'[{cmd!r} exited with {proc.returncode}]')
    #if stdout:
    #    print(f'[stdout]\n{stdout.decode()}')
    #if stderr:
    #    print(f'[stderr]\n{stderr.decode()}')
    return proc.returncode, stdout.decode(), stderr.decode()

async def download_file(session: aiohttp.ClientSession, url: str):
    async with session.get(url) as response:
        assert response.status == 200
        # For large files use response.content.read(chunk_size) instead.
        return await response.read()


client = discord.Client()

@client.event
async def on_message(message):
    # we do not want the bot to reply to itself
    if message.author == client.user:
        return

    # channel we received the message in
    channel = message.channel

    # bot was mentioned in the message with commands or help specified
    if client.user.mentioned_in(message) and ('commands' in message.content.lower() or 'help' in message.content.lower()):
        msg = 'Valid commands are:```\ncommands\nhelp\nstartclient\nstopclient\nstatusclient\nstartserver\nstopserver\nstatusserver\nupdateserver\nupdatebase\nupdateww2\nupdatenam\nupdatezombie\nmods: tempunitbaserepo,tempunitzombierepo,tempunitww2repo,tempunitvietnamrepo```'
        await channel.send(msg)

    # bot was mentioned in the message with the addmission directive
    elif client.user.mentioned_in(message) and 'addmission' in message.content.lower():
        with aiohttp.ClientSession() as session_down:
            bn = os.path.basename(message.attachments[0]['url'])
            result = "cd /home/steam/arma3/a3tu/mpmissions ; wget -O " + bn + " -c " + message.attachments[0]['url']
            #result, stdout, stderr = await run(get_command("addmission"))
            if result == 0:
                await channel.send('Download successful for: {0}'.format(message.attachments[0]['url']))
            else:
                await channel.send('Download failed for: {0}'.format(message.attachments[0]['url']))

    elif client.user.mentioned_in(message) and 'mods' in message.content.lower():
        rcv_msg = message.content.lower().split(' ',1)[1]
        repos = re.split(r'\s*:\s*',rcv_msg)[-1]
        repo_list = re.split(r'\s*,\s*',repos)
        allModPaths,shortModPaths = modPaths(repo_list)
        msg = 'Using the following mods:```{0}```'.format(shortModPaths)
        await channel.send(msg)
        writeFile('/home/steam/arma3/a3tu/profiles/A3TU_client.par',allModPaths)
        writeFile('/home/steam/arma3/a3tu/profiles/A3TU_server.par',allModPaths)

    # bot was mentioned in message
    elif client.user.mentioned_in(message):
        # break down each word in the message
        rcv_msg = message.content.lower().split(' ',1)[1]
        if get_command(script_commands_json,rcv_msg) == "error":
            msg = f'```Invalid Command```'
            await channel.send(msg)
        else:
            msg = f'```Executing: {get_command(script_commands_json,rcv_msg)}```'
            await channel.send(msg)
            # pass last word in message to get_command function
            result, stdout, stderr = await run(get_command(script_commands_json,rcv_msg))
            if result == 0:
                result = "Success"
            else:
                result = "Failed"
            await channel.send('```' + str(result) + '```')
            if stdout:
                await channel.send('```' + str(stdout) + '```')


@client.event
async def on_ready():
    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('------')


script_vars_json = (__file__).split('.')[0] + "_vars.json"
script_commands_json = (__file__).split('.')[0] + "_commands.json"

with open(script_vars_json,'r') as f:
    script_vars = json.load(f)

api_token = script_vars['api_token']
authorized_ids = script_vars['authorized_ids']
#mod_packs = script_vars['mod_packs']

client.run(api_token, bot=True)
