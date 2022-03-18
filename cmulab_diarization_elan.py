#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# ELAN recognizer that uses the speaker diarization API
# provided by the CMU Linguistic Annotation Backend

import atexit
import os
import os.path
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata

import requests
import json
import traceback
from utils.create_dataset import create_dataset_from_eaf
from credentials import ask_for_authtoken
import tkinter, tkinter.messagebox


# The set of annotations (dicts) parsed out of the given ELAN tier.
annotations = []

# The parameters provided by the user via the ELAN recognizer interface
# (specified in CMDI).
params = {}

@atexit.register
def cleanup():
    pass

def messagebox(title="", message=""):
    root = tkinter.Tk()
    root.overrideredirect(True)
    root.withdraw()
    tkinter.messagebox.showinfo(title=title, message=message)
    root.destroy()

# Read in all of the parameters that ELAN passes to this local recognizer on
# standard input.
for line in sys.stdin:
    match = re.search(r'<param name="(.*?)".*?>(.*?)</param>', line)
    if match:
        params[match.group(1)] = match.group(2).strip()

input_tier = params.get('input_tier', '')
print("input_tier: " + input_tier)
server_url = params['server_url'].strip().rstrip('/')
auth_token = params.get("auth_token", "").strip()
threshold = float(params.get("threshold", 0.45))

if not auth_token:
    auth_token_file = os.path.join(os.path.expanduser("~"), ".cmulab_diarization_elan")
    if os.path.exists(auth_token_file):
        with open(auth_token_file) as fin:
            auth_token = fin.read().strip()
    else:
        auth_token = ask_for_authtoken(server_url)

# grab the 'input_tier' parameter, open that
# XML document, and read in all of the annotation start times, end times,
# and values.
# Note: Tiers for the recognizers are in the AVATech tier format, not EAF
print("PROGRESS: 0.1 Loading annotations on input tier", flush = True)
if os.path.exists(input_tier):
    with open(input_tier, 'r', encoding = 'utf-8') as input_tier_file:
        for line in input_tier_file:
            match = re.search(r'<span start="(.*?)" end="(.*?)"><v>(.*?)</v>', line)
            if match:
                annotation = { \
                    'start': float(match.group(1)), \
                    'end' : float(match.group(2)), \
                    'value' : match.group(3) }
                annotations.append(annotation)

if not annotations:
    messagebox(title="ERROR", message="Please select an input tier containing a few sample speaker annotations.")
    print('RESULT: FAILED.', flush = True)
    sys.exit(1)


print("PROGRESS: 0.9 Running speaker diarization...", flush = True)
with open(params['source'],'rb') as audio_file:
    files = {'file': audio_file}
    url = params['server_url'].rstrip('/') + "/annotator/segment/1/annotate/2/"
    try:
        headers = {}
        if auth_token:
            headers["Authorization"] = auth_token
        request_params = {"service": "diarization", "threshold": threshold}
        print(url)
        print(params['source'])
        print(json.dumps(annotations, indent=4))
        print(json.dumps(request_params, indent=4))
        print(json.dumps(headers, indent=4))
        r = requests.post(url, files=files, data={"segments": json.dumps(annotations), "params": json.dumps(request_params)}, headers=headers)
    except:
        err_msg = "Error connecting to CMULAB server " + params['server_url']
        sys.stderr.write(err_msg + "\n")
        traceback.print_exc()
        messagebox(title="ERROR", message=err_msg)
        print('RESULT: FAILED.', flush = True)
        sys.exit(1)
    print("Response from CMULAB server " + params['server_url'] + ": " + r.text)
    if not r.ok:
        messagebox(title="ERROR", message="Server error, click the report button to view logs.")
        print('RESULT: FAILED.', flush = True)
        sys.exit(1)
    transcribed_annotations = json.loads(r.text)


print("PROGRESS: 0.95 Preparing output tier", flush = True)
with open(params['output_tier'], 'w', encoding = 'utf-8') as output_tier:
    # Write document header.
    output_tier.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    output_tier.write('<TIER xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" ' +
                      'xsi:noNamespaceSchemaLocation="file:avatech-tier.xsd" columns="CMULAB-Diarization">\n')

    for annotation in transcribed_annotations:
        output_tier.write('    <span start="%s" end="%s"><v>%s</v></span>\n' %
                          (annotation[1], annotation[2], annotation[0]))

    output_tier.write('</TIER>\n')

# Finally, tell ELAN that we're done.
print('RESULT: DONE.', flush = True)
