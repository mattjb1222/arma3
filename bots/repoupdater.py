#!/usr/bin/python3

import requests
import datetime
import argparse
import os
import re
import json
import subprocess
from collections import OrderedDict

def read_json(json_file):
    with open(json_file,'r') as f:
        return json.load(f, object_pairs_hook=OrderedDict)

def write_json(json_data, json_file):
    with open(json_file,'w') as f:
        json.dump(json_data, f, indent=4, separators=(',', ': '))

def show_json(json_data):
    json.dumps(json_data, indent=4, separators=(',',': '))

def rebuild(a3sync_path, java_path, repo):
    os.chdir(a3sync_path)
    args = [java_path, '-jar', 'ArmA3Sync.jar', '-BUILD', repo]
    child = subprocess.Popen(args, stdout=subprocess.PIPE)
    stream = child.communicate()[0]
    #print(stream)
    with open('/var/www/html/' + repo.lower() + '/.a3s/.htaccess','w') as f:
        f.write("Satisfy Any")
    return child.returncode

def create_steam_batch(steam_user, scripts_path, steam_apps_path, mod):
    #print("Creating steam batch script...")
    with open(scripts_path + '/steam_script.' + str(os.getpid()), 'w') as f:
        f.write("@ShutdownOnFailedCommand 0\n")
        f.write("@NoPromptForPassword 1\n")
        f.write("login %s\n" % (steam_user))
        f.write("force_install_dir %s\n" % steam_apps_path)
        f.write("workshop_download_item 107410 %s\n" % mod)
        f.write("quit\n")
    return format("%s/steam_script.%s" % (scripts_path, os.getpid()))

def download_mod(steam_cmd_bin, steam_batch):
    args = [steam_cmd_bin, '+runscript', steam_batch]
    child = subprocess.Popen(args, stdout=subprocess.PIPE)
    stream = child.communicate()[0]
    os.remove(steam_batch)
    return child.returncode

def rsync_files(steam_apps_path, id, path):
    args = ['rsync', '--delete','-Pvvhra', steam_apps_path + "/steamapps/workshop/content/107410/" + id + "/", repos[repo][id]["path"]]
    child = subprocess.Popen(args, stdout=subprocess.PIPE)
    stream = child.communicate()[0]
    return child.returncode

def delete_download_dir(steam_apps_path, id):
    if os.path.exists(steam_apps_path + "/steamapps/workshop/content/107410/" + id + "/"):
        args = ['rm', '-rf', steam_apps_path + "/steamapps/workshop/content/107410/" + id + "/"]
        child = subprocess.Popen(args, stdout=subprocess.PIPE)
        stream = child.communicate()[0]
        return child.returncode
    else:
        return

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

# load existing repo data
repos_json = os.path.dirname(os.path.abspath(__file__)) + "/repos.json"
repos = read_json(repos_json)

for repo in repos:
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

#
# Create steam script and download workshop mod
#
for repo in repos:
    for id in repos[repo]:
        if not repos[repo][id]['enabled']:
            continue
        if repos[repo][id]['update']: 
            #print("Creating steam batch for %s" % id)
            steam_batch = create_steam_batch(steam_user, scripts_path, steam_apps_path, id)

            attempt = 0
            while attempt < 10:
                return_code = download_mod(steam_cmd_bin, steam_batch)
                #print("RC: %s" % return_code)
                if return_code == 0:
                    repos[repo][id]['update'] = False
                    repos[repo][id]['rsync'] = True
                    break
                attempt += 1

write_json(repos, repos_json)

#
# Rsync files from workshop dir to the repo dir
#
for repo in repos:
    for id in repos[repo]:
        if not repos[repo][id]['enabled']:
            continue
        if repos[repo][id]['rsync']:
            return_code = rsync_files(steam_apps_path, id, repos[repo][id]['path'])
            if return_code == 0:
                repos[repo][id]['rsync'] = False
                repos[repo][id]['rebuild'] = True
                delete_download_dir(steam_apps_path, id)

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
