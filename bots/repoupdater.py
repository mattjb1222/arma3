#!/usr/bin/python3

import requests
import argparse
import os
import re
import json
import sys
import subprocess
import shutil
import shlex
import logging
import time
import fcntl
from datetime import datetime
from collections import OrderedDict

def lock_pid(pid_file):
  fp = open(pid_file, 'w')
  try:
    fcntl.lockf(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
    print("locked {}".format(pid_file))
    return True, fp
  except IOError:
    return False, fp

def read_json(json_file):
    with open(json_file,'r') as f:
        return json.load(f, object_pairs_hook=OrderedDict)

def write_json(json_data, json_file):
    with open(json_file,'w') as f:
        json.dump(json_data, f, indent=4, separators=(',', ': '))

def show_json(json_data):
    json.dumps(json_data, indent=4, separators=(',',': '))

def run(cmd):
    args = shlex.split(cmd)
    child = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = child.communicate()
    return out.decode(), err.decode(), child.returncode

def rebuild(a3sync_path, java_path, repo):
    os.chdir(a3sync_path)
    cmd = java_path + ' -jar ArmA3Sync.jar -BUILD ' + repo
    out, err, rc = run(cmd)
    logging.info("rebuild out: {}".format(str(out)))
    if err:
        logging.error("rebuild err: {}".format(str(err)))
    with open('/var/www/html/' + repo.lower() + '/.a3s/.htaccess','w') as f:
        f.write("Satisfy Any")
    return rc

def create_steam_batch(steam_user, scripts_path, steam_apps_path, mod):
    with open(scripts_path + '/steam_script.' + str(os.getpid()), 'w') as f:
        f.write("@ShutdownOnFailedCommand 0\n")
        f.write("@NoPromptForPassword 1\n")
        f.write("login %s\n" % (steam_user))
        f.write("force_install_dir %s\n" % steam_apps_path)
        f.write("workshop_download_item 107410 %s\n" % mod)
        f.write("quit\n")
    return format("%s/steam_script.%s" % (scripts_path, os.getpid()))

def download_mod(steam_cmd_bin, steam_batch):
    cmd = steam_cmd_bin + ' +runscript ' + steam_batch
    out, err, rc = run(cmd)
    logging.info("download_mod out for {}: {}".format(str(steam_batch),str(out)))
    if err:
        logging.error("download_mod err for {}: {}".format(str(steam_batch),str(err)))
    else:
        os.remove(steam_batch)
    return rc, out, err

def rsync_files(steam_apps_path, id, path):
    cmd = 'rsync --delete -Pvvhra ' + steam_apps_path + '/steamapps/workshop/content/107410/' + str(id) + '/ ' + repos[repo][id]['path']
    out, err, rc = run(cmd)
    logging.info("rsync out for {}: {}".format(str(id),str(out)))
    if err:
        logging.error("rsync err for {}: {}".format(str(id),str(err)))
    return rc

def delete_download_dir(steam_apps_path, id):
    if os.path.exists(steam_apps_path + "/steamapps/workshop/content/107410/" + id + "/"):
        shutil.rmtree(steam_apps_path + "/steamapps/workshop/content/107410/" + id + "/")
        logging.info("deleted {}".format(steam_apps_path + "/steamapps/workshop/content/107410/" + id + "/"))
    else:
        return

def discord_msg(bot_token, channel_id, msg):
    base_url = "https://discordapp.com/api/channels/{}/messages".format(channel_id)
    headers = { "Authorization":"Bot {}".format(bot_token),
                "User-Agent":"myBotThing (http://some.url, v0.1)",
                "Content-Type":"application/json", }
    posted_json =  json.dumps ( {"content":msg} )
    r = requests.post(base_url, headers = headers, data = posted_json)

with open(os.path.dirname(os.path.abspath(__file__)) + "/repoupdater_vars.json",'r') as f:
    vars = json.load(f)
    toEmail = vars['toEmail']
    fromEmail = vars['fromEmail']
    scripts_path = vars['scripts_path']
    a3sync_path = vars['a3sync_path']
    java_path = vars['java_path']
    steam_apps_path = vars['steam_apps_path']
    steam_cmd_bin = vars['steam_cmd_bin']
    steam_user = vars['steam_user']
    emailmsg = vars['emailmsg']
    discordmsg = vars['discordmsg']
    bot_token = vars['bot_token']
    channel_id = vars['channel_id']

# logging module configuration
FORMAT = '%(asctime)-15s: %(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT)

# Determine if pid is locked, if locked, then exit, we don't want duplicate instances running
locked, file_pid = lock_pid('/tmp/repoupdater.pid')
if not locked:
    print("Script already running... exiting.")
    sys.exit(0)

# load existing repo data
repos_json = os.path.dirname(os.path.abspath(__file__)) + "/repos.json"
repos = read_json(repos_json)

parser = argparse.ArgumentParser(description='Repo management and update script.')

parser.add_argument('-repo',
                    action='store',
                    dest='repository',
                    metavar='<RepositoryName>',
                    required=False,
                    help='Repository name in camel case')
parser.add_argument('-id',
                    action='store',
                    dest='mod_id',
                    metavar='<workshop_id>',
                    required=False,
                    help='Workshop ID')
parser.add_argument('-title',
                    action='store',
                    dest='mod_title',
                    metavar='"<workshop_title>"',
                    required=False,
                    help='Workshop Title')
parser.add_argument('-path',
                    action='store',
                    dest='mod_path',
                    metavar='"<mod_path>"',
                    required=False,
                    help='Path to mod')
parser.add_argument('-list',
                    action='store_true',
                    dest='mod_list',
                    required=False,
                    help='List repos, its addons, and variables')
parser.add_argument('-rebuild',
                    action='store_true',
                    dest='rebuild_repo',
                    required=False,
                    help='Forces rebuild of the specified repository')
parser.add_argument('-add',
                    action='store_true',
                    dest='add',
                    required=False,
                    help='Adds ID')
parser.add_argument('-remove',
                    action='store_true',
                    dest='remove',
                    required=False,
                    help='Removes ID')
parser.add_argument('-noemail',
                    action='store_true',
                    dest='noemail',
                    required=False,
                    help='No email on update')
parser.add_argument('-nodiscord',
                    action='store_true',
                    dest='nodiscord',
                    required=False,
                    help='No discord message on update')
parser.add_argument('-debug',
                    action='store_true',
                    dest='debug',
                    required=False,
                    help='Show debug')

args = parser.parse_args()

repository = args.repository
mod_id = args.mod_id
mod_title = args.mod_title
mod_path = args.mod_path
mod_list = args.mod_list
rebuild_repo = args.rebuild_repo
add = args.add
remove = args.remove
noemail = args.noemail
nodiscord = args.nodiscord
debug = args.debug

if repository and mod_list:
    print(json.dumps(repos[repository], indent=4, separators=(',',': ')))
    sys.exit(0)
elif repository and add and mod_id and mod_path:
    repos[repository][mod_id] = OrderedDict()
    if mod_title:
        repos[repository][mod_id]['title'] = mod_title
    else:
        repos[repository][mod_id]['title'] = ''
    repos[repository][mod_id]['size'] = ''
    repos[repository][mod_id]['created'] = ''
    repos[repository][mod_id]['modified'] = ''
    repos[repository][mod_id]['update'] = True
    repos[repository][mod_id]['rsync'] = False
    repos[repository][mod_id]['rebuild'] = False
    repos[repository][mod_id]['enabled'] = True
    repos[repository][mod_id]['path'] = mod_path
    print(json.dumps(repos[repository][mod_id], indent=4, separators=(',',': ')))
    if not os.path.exists(repos[repository][mod_id]['path']):
        os.makedirs(repos[repository][mod_id]['path'])
    write_json(repos, repos_json)
    sys.exit(0)
elif repository and remove and mod_id:
    try:
        if os.path.exists(repos[repository][mod_id]['path']):
            shutil.rmtree(repos[repository][mod_id]['path'])
        del repos[repository][mod_id]
        write_json(repos, repos_json)
        sys.exit(0)
    except KeyError:
        sys.exit(0)
elif repository and rebuild_repo:
    return_code = rebuild(a3sync_path, java_path, repository)
    sys.exit(0)
elif mod_list:
    print(json.dumps(repos, indent=4, separators=(',',': ')))
    sys.exit(0)

#
# No arguments specified, assume update for all repos
#
for repo in repos:
    # skip all other repositories if repo is defined
    if repository and repo != repository:
        continue

    # update each object with new information
    for id, val in sorted(repos[repo].items(), key=lambda x: x[1]['title']):
        # check if mod is enabled to be updated
        if not repos[repo][id]['enabled']:
            continue

        # retrieve steamcommunity page for workshop id
        r = requests.get('https://steamcommunity.com/sharedfiles/filedetails/?id=' + id)

        # search for title
        title = re.search(r'Steam Workshop :: (.*)</t',r.text)

        # search for size, created, modified (if exists)
        m = re.findall(r'detailsStatRight.*>(.*)</div>',r.text)
        if title:
            repos[repo][id]['title'] = title.group(1)
        if m:
            repos[repo][id]['size'] = m[0]
            if repos[repo][id]['created'] != m[1]:
                repos[repo][id]['created'] = m[1]
            try:
                if repos[repo][id]['modified'] != m[2]:
                    repos[repo][id]['modified'] = m[2]
                    repos[repo][id]['update'] = True
            except:
                repos[repo][id]['modified'] = m[1]
        logging.info("ID: {} -- Title: {} -- Update: {}".format(id,repos[repo][id]['title'], repos[repo][id]['update']))

write_json(repos, repos_json)

#
# Create steam script and download workshop mod
#
for repo in repos:
    for id in repos[repo]:
        if not repos[repo][id]['enabled']:
            continue
        if repos[repo][id]['update']: 
            steam_batch = create_steam_batch(steam_user, scripts_path, steam_apps_path, id)

            #attempt = 0
            #while attempt < 10:
            logging.info("Starting download for: {}".format(repos[repo][id]['title']))
            return_code, download_out, download_err = download_mod(steam_cmd_bin, steam_batch)
            if return_code == 0 and not re.search(r"[Tt]imeout downloading",download_out):
                repos[repo][id]['update'] = False
                repos[repo][id]['rsync'] = True
                break
            #attempt += 1

write_json(repos, repos_json)

#
# Rsync files from workshop dir to the repo dir
#
for repo in repos:
    updated_mods = {}
    for id in repos[repo]:
        if not repos[repo][id]['enabled']:
            continue
        if repos[repo][id]['rsync']:
            return_code = rsync_files(steam_apps_path, id, repos[repo][id]['path'])
            if return_code == 0:
                repos[repo][id]['rsync'] = False
                updated_mods[id] = repos[repo][id]['title']
                repos[repo][id]['rebuild'] = True
                delete_download_dir(steam_apps_path, id)
    #
    # Report to Discord anything that was updated
    #
    if updated_mods:
        msg = "<@&334491572748156928> Following were updated: ```\n"
        for k,v in updated_mods.items():
            msg = msg + k + ": " + v + " -- (" + repos[repo][k]['modified'] + " Pacific Time) \n"
        msg = msg + '```'
        if not nodiscord:
            discord_msg(bot_token, channel_id, msg)

write_json(repos, repos_json)

#
# Rebuild repository if an update was made
#
rebuilt = {}
for repo in repos:
    rebuilt[repo] = False 
    for id in repos[repo]:
        if not repos[repo][id]['enabled']:
            continue
        if repos[repo][id]['rebuild']:
            if rebuilt[repo]:
                repos[repo][id]['rebuild'] = False
            else:
                return_code = '1'
                return_code = rebuild(a3sync_path, java_path, repo)
                if return_code == 0:
                    repos[repo][id]['rebuild'] = False
                    rebuilt[repo] = True

write_json(repos, repos_json)

if file_pid:
    file_pid.close()
