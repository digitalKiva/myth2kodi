#! /usr/bin/env python
# -*- coding: UTF-8 -*-
# ---------------------------
"""
---------------------------
Name: myth2kodi.py
Author: jncl
Version: 0.1.36
Description:
   A script for generating a library of MythTV show recordings for Kodi(XBMC). The key feature of this script is that
   "Specials" (episodes with the same series title, but missing show and episode info) are grouped together under the
   **same series** for easy navigation in Kodi. To generate the library, recordings are linked, and metadata and
   image links (posters, fanart, and banners) for each series are pulled from either TheTVDB or TheMovieDB depending
   on the "inetref" value in MythTV. Commercial detection is done with comskip.
---------------------------
"""

# Needs to check if a recording has been deleted and if so, don't process it

import httplib

import os
import xml.etree.cElementTree as ET
from lxml import etree as ET2
import xml.dom.minidom as dom
import urllib2
import re
import argparse
import zipfile
from PIL import Image
import cStringIO
import json
import sys
import subprocess
import config
import logging
from logging.handlers import TimedRotatingFileHandler

reload(sys)
sys.setdefaultencoding('utf-8')

BASE_URL = "http://" + config.hostname + ":" + config.host_port
THIS_DIR = os.getcwd()
log_content = ''
log = None

parser = argparse.ArgumentParser(__file__,
                                 description='myth2kodi... A script to enable viewing of MythTV recordings in XBMC(Kodi)\n' +
                                             '\n' +
                                             'On GitHub: https://github.com/joncl/myth2kodi\n' +
                                             '\n' +
                                             'NOTES:\n' +
                                             ' - At least one argument is required.\n' +
                                             ' - Use --scan-all or --comskip-all separately to either scan for new MythTV recordings or\n' +
                                             '   scan for commercials in existing MythTV recordings already linked.\n' +
                                             ' - Create a MythTV user job with -add <path to MythTV mpg> to add a new MythTV recording.\n' +
                                             '   The new recording will be scanned for commercials after it is added.\n',
                                 formatter_class=argparse.RawTextHelpFormatter)
parser.add_argument('--add', dest='add', action='store', metavar='<path to mpg file>',
                    help="Full path to file name of MythTV recording, used for a MythTV user job upon 'Recording Finished'.")
parser.add_argument('--add-all', dest='add_all', action='store_true', default=False,
                    help='Add all MythTV recordings that are missing.')
parser.add_argument('--show-status', dest='show_status', action='store_true', default=False,
                    help='Print the output status showing total and new series, episodes, and specials. This will not write any new links or files.')
parser.add_argument('--comskip', dest='comskip', action='store', metavar='<path to mpg file>',
                    help="Full path to file name of MythTV recording, used to comskip just a single recording.")
parser.add_argument('--comskip-all', dest='comskip_all', action='store_true', default=False,
                    help='Run comskip on all video files found recursively in the "destination_dir" path from config.py.')
parser.add_argument('--comskip-off', dest='comskip_off', action='store_true', default=False,
                    help='Turn off comskip when adding a single recording with --add.')
parser.add_argument('--comskip-status', dest='comskip_status', action='store_true', default=False,
                    help='Report linked recordings with missing comskip files.')
parser.add_argument('--add-match-title', dest='add_match_title', action='store', metavar='<title match>',
                    help='Process only recordings with titles that contain the given query.')
parser.add_argument('--add-match-programid', dest='add_match_programid', action='store', metavar='<programid match',
                    help='Process only recordings that match the given program id.')
parser.add_argument('--export-recording-list', dest='export_recording_list', action='store_true', default=False,
                    help='Export the entire MythTV recording list to recording_list.xml.')
parser.add_argument('--print-match-filename', dest='print_match_filename', action='store',
                    metavar='<mpg file name match>',
                    help='Show recording xml for a recording with the same mpg file name as the given file name.')
parser.add_argument('--print-match-title', dest='print_match_title', action='store', metavar='<title match>',
                    help='Print recording xml for recordings with titles that contain the given query.')
parser.add_argument('--print-config', dest='print_config', action='store_true',
                    help='Prints all the config variables and values in the config.py file.')
parser.add_argument('--import-recording-list', dest='import_recording_list', action='store',
                    metavar='<path to xml file',
                    help='Import recording list in xml format. Specify full path to xml file.')
parser.add_argument('--log-debug', dest='log_debug', action='store_true', default=False,
                    help='Write debug messages to the log file. Default logging level is INFO.')
parser.add_argument('--refresh-nfos', dest='refresh_nfos', action='store_true', default=False,
                    help='Refresh nfo files. Can be combined with --add to refresh specific nfo file.')

# TODO: handle arguments refresh nfos
# TODO: clean up symlinks, nfo files, and directories when MythTV recordings are deleted
# parser.add_argument('-r', '--refresh-nfos', dest='refresh_nfos', action='store_true', default=False,
# help='refresh all nfo files')
# parser.add_argument('-c', '--clean', dest='clean', action='store_true', default=False,
# help='remove all references to deleted MythTV recordings')
# parser.add_argument('--rebuild-library', dest='rebuild_library', action='store_true', default=False,
# help='rebuild library from existing links')

if len(sys.argv) == 1:
    parser.error('At lease one argument is required. Use -h or --help for details.')
    sys.exit(1)

args = parser.parse_args()
# print args.print_match_filename
args_add_match_title = None
if args.add_match_title is not None:
    args_add_match_title = unicode(args.add_match_title)


def get_script_path():
    return os.path.dirname(os.path.realpath(sys.argv[0]))


def initialize_logging():
    global log
    handler = TimedRotatingFileHandler(os.path.join(get_script_path(), 'myth2kodi.log'), when='midnight', backupCount=5)
    formatter = logging.Formatter('[%(asctime)s.%(msecs)03d] [%(levelname)7s] - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    handler.setFormatter(formatter)
    log = logging.getLogger('myth2kodi')
    log.addHandler(handler)
    if args.log_debug is True:
        log.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.INFO)

    log.debug('Logging initialized')
    log.info('')

def log_missing_inet_ref(title):
    return


def prettify(xml_element):
    """
    format xml
    :param xml_element: xml element to format
    :return: formatted xml element
    """
    rough_string = ET.tostring(xml_element, 'utf-8')
    reparsed = dom.parseString(rough_string)
    return reparsed.toprettyxml(indent="\t")

def write_comskip(base_link_file, mark_dict):
    if not len(mark_dict):
        return

    c = 'FILE PROCESSING COMPLETE\r\n'
    c = c + '------------------------\r\n'
    for start, end in mark_dict.iteritems():
        c = c + '{} {}\r\n'.format(start, end)

    f = open(base_link_file + '.txt', 'a')
    f.write(c)
    f.close()


def series_nfo_exists(directory):
    """
    check if series nfo file tvshow.nfo exists
    :param directory: directory to check for nfo file
    :return: True exists, or False does not exist
    """
    return os.path.exists(os.path.join(directory, 'tvshow.nfo'))


def check_recordings_dirs():
    """
    checks mythtv recording directories listed in config.py under myth_recording_dir
    """
    for myth_recording_dir in config.mythtv_recording_dirs[:]:
        if os.path.exists(myth_recording_dir) is not True:
            print myth_recording_dir + " is not a valid path. Aborting"


def get_base_filename_from(path):
    """
    return the base filename
    :param path:
    :return: base filename
    """
    return os.path.splitext(os.path.basename(path))[0]


def get_series_id(inetref):
    """
    regex just the id # from a ttvdb or tmdb internet reference
    :param inetref: internet reference stored in MythTV
    :return: series id #
    """
    return re.findall('[\d]+$', inetref)[0]


def download_file(file_url, target_file='', return_response=False):
    global log
    if return_response is False:
        log.info('Saving: ' + file_url)
        log.info('    to: ' + target_file)
    try:
        req = urllib2.Request(file_url)
        response = urllib2.urlopen(req)
        if return_response is True:
            return response
        if response is None:
            return False
        output = open(target_file, 'wb')
        output.write(response.read())
        output.close()
    except urllib2.HTTPError, e:
        log.error('HTTPError = ' + str(e.code))
        return False
    except urllib2.URLError, e:
        log.error('URLError = ' + e.reason)
        return False
    except httplib.HTTPException, e:
        log.error('HTTPException')
        return False
    except Exception:
        import traceback

        log.error('generic exception: ' + traceback.format_exc())
        return False
    else:
        return True

def get_title_from_ttvdb(inetref):
    # store series zip from thetvdb.com
    """
    create a new show from a ttvdb id
    :param inetref:
    :return: The TTVDb series name.
    """
    global log
    ttvdb_base_url = 'http://www.thetvdb.com/'
    series_id = get_series_id(inetref)
    series_zip_file = os.path.join(config.ttvdb_zips_dir, series_id + '.zip')
    if not os.path.exists(series_zip_file):
        # zip does not exist, download it
        # print '    downloading ttvdb zip file...'
        log.info('TTVDB zip does not exist, downloading ttvdb zip file to: ' + series_zip_file)
        ttvdb_zip_file = ttvdb_base_url + 'api/' + config.ttvdb_key + '/series/' + series_id + '/all/en.zip'
        download_file(ttvdb_zip_file, series_zip_file)
        # urllib.urlretrieve(ttvdb_zip_file, series_zip_file)

    # extract poster, banner, and fanart urls
    # print '    ttvdb zip exists, reading xml contents...'
    log.info('ttvdb zip exists, reading xml contents...')
    z = zipfile.ZipFile(series_zip_file, 'r')
    for name in z.namelist():
        if name == 'en.xml':
            z.extract(name, '/tmp/')
            break
    if not os.path.exists('/tmp/en.xml'):
        print '    en.xml not found in series zip file at /tmp/en.xml'
        log.error('en.xml not found in series zip file at /tmp/en.xml')
        return False
    else:
        log.info('Reading en.xml...')
        tree = ET.parse('/tmp/en.xml')
        series_data = tree.getroot()
        series = series_data.find('Series')
        if series is None:
            log.error('Could not find the "Series" section in en.xml.')
            return False

        title = series.find('SeriesName').text

        return title

def print_config():
    print ''
    print 'config.py:'
    print '    hostname:            ' + unicode(config.hostname)
    print '    host_port:           ' + unicode(config.host_port)
    print '    myth_recording_dirs: ' + unicode(config.mythtv_recording_dirs)
    print '    destination_dir:        ' + unicode(config.destination_dir)
    print '    ttvdb_key:           ' + unicode(config.ttvdb_key)
    print '    ttvdb_zips_dir:      ' + unicode(config.ttvdb_zips_dir)
    print '    tmdb_key:            ' + unicode(config.tmdb_key)
    print ''


def get_recording_list():
    """
    get recorded list from mythtv database or from xml file specified with --import-recording-list argument

    :return: xml parsed recorded list
    """
    global log
    if args.import_recording_list is not None:
        log.info('Importing recording list from: ' + args.import_recording_list)
        if not os.path.exists(args.import_recording_list):
            log.error('--import-recording-list was specified but xml file was not found.')
            raise Exception()
        else:
            path = os.path.join('file://', args.import_recording_list)
            tree = ET.parse(path)
    else:
        url = BASE_URL + '/Dvr/GetRecordedList'
        log.info('Looking up from MythTV: ' + url)
        tree = ET.parse(urllib2.urlopen(url))
    # print prettify(tree.getroot())
    # sys.exit(0)
    return tree.getroot()


def comskip_file(root_path, file):
    global log
    if file.lower().endswith('.mpg'):
        base_file = os.path.splitext(file)[0]
        txt_file = os.path.join(root_path, base_file + '.txt')
        log_file = os.path.join(root_path, base_file + '.log')
        logo_file = os.path.join(root_path, base_file + '.logo.txt')
        edl_file = os.path.join(root_path, base_file + '.edl')

        # if txt file exists, then skip this mpg
        if os.path.exists(txt_file):
            log.info('Skipping comskip (txt file exists) for: ' + file)
            return False

        # run comskip
        log.info('Running comskip on: ' + os.path.join(root_path, file))
        base_comskip_dir = os.path.dirname(config.comskip_exe)
        log.debug('Changing directory to: ' + base_comskip_dir)
        os.chdir(base_comskip_dir)
        command = 'wine {} "{}"'.format(config.comskip_exe, os.path.join(root_path, file))
        log.debug('Calling comskip with:')
        log.debug(command)
        try:
            exit_code = subprocess.call(command, shell=True)
            log.info('Comskip completed.'.format(str(exit_code)))
        except Exception, e:
            log.error('Exception encountered running comskip...')
            log.error(str(e))

        os.chdir(THIS_DIR)

        # remove extra files
        if os.path.exists(log_file):
            os.remove(log_file)
        if os.path.exists(logo_file):
            os.remove(logo_file)
        if os.path.exists(edl_file):
            os.rename(edl_file, edl_file + '.bak')

        return True


def comskip_all():
    global log
    log.info('compskip_all()')
    count = comskip_status(return_missing_count=True)
    if count == 0:
        log.info('No missing comskip files were found.')
        print('No missing comskip files were found.')
    else:
        log.info('Running comskip on ' + str(count) + ' recordings with missing comskip files...')
        for root, dirs, files in os.walk(config.destination_dir):
            # print root
            # path = root.split('/')
            # print path
            # print (len(path) - 1) *'---' , os.path.basename(root)
            for file in files:
                comskip_ran = comskip_file(root, file)
                if comskip_ran is True:
                    log.info(str(count) + ' recordings left to comskip.')
                    count -= 1


def comskip_status(return_missing_count=False):
    comskip_missing_lib = []
    for root, dirs, files in os.walk(config.destination_dir):
        # print root
        # path = root.split('/')
        # print path
        # print (len(path) - 1) *'---' , os.path.basename(root)
        for file in files:
            if file.lower().endswith('.mpg'):
                base_file = os.path.splitext(file)[0]
                txt_file = os.path.join(root, base_file + '.txt')
                edl_file = os.path.join(root, base_file + '.edl.bak')
                if os.path.exists(txt_file) and os.path.exists(edl_file):
                    continue
                comskip_missing_lib.append(os.path.join(root, file))
    count = len(comskip_missing_lib) - 1
    if return_missing_count is True:
        return count
    message = '  Found ' + str(len(comskip_missing_lib) - 1) + ' recordings with missing comskip files.'
    if count > 0:
        message += ' Use "--comskip-all" to process them.'
    print ''
    print message
    print ''


def write_recording_list(recording_list):
    global log
    log.info('Writing recording list.')
    f = open('recording_list.xml', 'w')
    f.write(prettify(recording_list))
    f.close()
    log.info('Done writing recording list.')

def read_recordings():
    """
    read MythTV recordings

    """
    global log
    print ''
    series_lib = []
    series_new_lib = []
    episode_count = 0
    episode_new_lib = []
    special_count = 0
    special_new_lib = []
    image_error_list = []
    updated_nfos_lib = []

    recording_list = get_recording_list()

    #print prettify(recording_list)

    if args.export_recording_list is True:
        write_recording_list(recording_list)
        return True

    for recording in recording_list.iter('Program'):
        is_special = False

        #print prettify(recording)
   
        # collect program attributes
        mythtv_title = unicode(recording.find('Title').text)
        subtitle = unicode(recording.find('SubTitle').text)
        season = unicode(recording.find('Season').text)
        episode = unicode(recording.find('Episode').text.zfill(2))
        air_date = unicode(recording.find('Airdate').text)
        plot = unicode(recording.find('Description').text)
        category = unicode(recording.find('Category').text)
        inetref = unicode(recording.find('Inetref').text)
        program_id = unicode(recording.find('ProgramId').text)
        recording_group = unicode(recording.find('Recording/RecGroup').text)
        file_name = recording.find('FileName').text

        #if subtitle is None or subtitle == 'None':
        #    subtitle = 'Generic Episode'

        # print mythtv_title + subtitle + inetref

        # be sure we have an inetref
        if inetref is None or inetref == '' or inetref == 'None':
            log.warning('Inetref was not found, cannot process: ' + mythtv_title + subtitle)
            continue

        # Use the TVDB title from here on in
        ttvdb_title = get_title_from_ttvdb(inetref)
        #ttvdb_title = re.sub('[\[\]/\\;><&*:%=+@!#^()|?]', '', ttvdb_title)
        #ttvdb_title = re.sub(' +', ' ', ttvdb_title)

        # Skip deleted recordings
        if recording_group == 'Deleted':
            log.info('Ignoring deleted recording: ' + ttvdb_title + ' - ' + subtitle)
            continue

        # check if we're adding a new file by comparing the current file name to the argument file name
        base_file_name = get_base_filename_from(file_name)
        if args.add is not None:
            if not base_file_name == get_base_filename_from(args.add):
                continue
            log.info('Adding new file with "--add {}"'.format(args.add))
            print 'ADDING NEW RECORDING: ' + args.add

        # print recording info if --print_match_filename arg is given
        if args.print_match_filename is not None:
            if args.print_match_filename in base_file_name:
                print prettify(recording)
                sys.exit()
            else:
                continue

        # check if we are matching on a title
        if args_add_match_title is not None:
            if args_add_match_title not in ttvdb_title:
                continue

        # print recording info if argument give is in title
        if args.print_match_title is not None and args.print_match_title in ttvdb_title:
            print prettify(recording)
            continue

        # check if we are matching on a program id
        if args.add_match_programid is not None:
            if not args.add_match_programid == program_id:
                continue
            else:
                print('PROGRAM ID MATCH: ' + program_id)
                print('title: ' + ttvdb_title)
                print('plot: ' + plot)

        file_extension = file_name[-4:]
        log.info('PROCESSING PROGRAM:')
        log.info('Title: ' + ttvdb_title + subtitle)
        log.info('Filename: ' + base_file_name + file_extension)
        log.info('Inetref: ' + inetref)

        # if it's a special...
        if season.zfill(2) == "00" and episode == "00":
            # episode_name = episode_name + " - " + air_date
            # air_date = record_date  # might be needed so specials get sorted with recognized episodes
            is_special = True
            special_count += 1
        else:
            episode_count += 1

        # parse show name for file system safe name
        #title_safe = re.sub('[\[\]/\\;><&*:%=+@!#^()|?]', '', title)
        #title_safe = re.sub(' +', ' ', title_safe)

        # form the file name
        episode_name = ttvdb_title + " - S" + season + "E" + episode + " - " + subtitle

        # set target link dir
        target_link_dir = os.path.join(config.destination_dir, ttvdb_title)
        link_file = os.path.join(target_link_dir, episode_name) + file_extension

        # check if we're running comskip on just one recording
        if args.comskip is not None:
            if base_file_name == get_base_filename_from(args.comskip):
                log.info('Running comskip on ' + args.comskip)
                comskip_file(os.path.dirname(link_file), os.path.basename(link_file))
                break

        # update series library and count
        if not series_lib or ttvdb_title not in series_lib:
            series_lib.append(ttvdb_title)

        # skip if link already exists
        if os.path.exists(link_file) or os.path.islink(link_file):
            print 'Link already exists: ' + link_file
            log.info('Link already exists: ' + link_file)
            continue

        # find source directory, and if not found, skip it because it's an orphaned recording!
        # (skip this if we are reading from an xml file)
        if args.import_recording_list is None:
            source_dir = None
            for mythtv_recording_dir in config.mythtv_recording_dirs[:]:
                source_file = os.path.join(mythtv_recording_dir, base_file_name) + file_extension
                if os.path.isfile(source_file):
                    source_dir = mythtv_recording_dir
                    break

            if source_dir is None:
                # could not find file!
                # print ("Cannot create link for " + episode_name + ", no valid source directory.  Skipping.")
                log.error('Cannot create link for ' + episode_name + ', no valid source directory.  Skipping.')
                continue

        # this is a new recording, so check if we're just checking the status for now
        if args.show_status is True and is_special is True:
            if not os.path.exists(link_file):
                special_new_lib.append(link_file)
            continue

        #series_title = get_title_from_ttvdb(inetref)

        #title_safe = re.sub('[\[\]/\\;><&*:%=+@!#^()|?]', '', series_title)
        #title_safe = re.sub(' +', ' ', title_safe)

        target_link_dir = os.path.join(config.destination_dir, ttvdb_title)

        #if not os.path.exists(target_link_dir) or (os.path.exists(target_link_dir) and not (os.path.exists(os.path.join(target_link_dir, 'tvshow.nfo')))):
        if not os.path.exists(target_link_dir):
            os.makedirs(target_link_dir)

                #result = new_series_from_ttvdb(title, ttvdb_title, inetref, category, target_link_dir)
                #print "RESULT: " + result


        #target_link_dir = os.path.join(config.destination_dir, ttvdb_title)
        episode_name = ttvdb_title + " - S" + season + "E" + episode + " - " + subtitle
        link_file = os.path.join(target_link_dir, episode_name) + file_extension

        # create link
        # print "Linking " + source_file + " ==> " + link_file
        if args.show_status is False and args.import_recording_list is None and args.refresh_nfos is False:
            if not os.path.exists(link_file) or not os.path.islink(link_file):
                log.info('Linking ' + source_file + ' ==> ' + link_file)
                if config.target_type == "symlink":
                    os.symlink(source_file, link_file)
                elif config.target_type == "hardlink":
                    os.link(source_file, link_file)
        # commercial skipping didn't work reliably using frames markers from the mythtv database as of .27
        # keep the code here anyway for later reference
        # write_comskip(path, mark_dict)

        # count new episode or special
        if not os.path.exists(link_file):
            if is_special is True:
                special_new_lib.append(link_file)
                # special_new_count += 1
            else:
                # episode_new_count += 1
                episode_new_lib.append(link_file)

        # count number of updated nfo files
        if args.refresh_nfos is True:
            updated_nfos_lib.append(source_file)

        # if adding a new recording with --add, comskip it, and then stop looking
        if args.add is not None and args.show_status is False:
            if args.comskip_off is False:
                # using comskip for commercial detection: http://www.kaashoek.com/comskip/
                comskip_file(os.path.dirname(link_file), os.path.basename(link_file))
            break

    if args.add is None and args.show_status is True and args.refresh_nfos is False:
        print '   --------------------------------'
        print '   |         |  Series:   ' + str(len(series_lib))
        print '   |  Total  |  Episodes: ' + str(episode_count)
        print '   |         |  Specials: ' + str(special_count)
        print '   |-------------------------------'
        print '   |         |  Series:   ' + str(len(series_new_lib))
        print '   |   New   |  Episodes: ' + str(len(episode_new_lib))
        print '   |         |  Specials: ' + str(len(special_new_lib))
        print '   --------------------------------'
        print '   |  Image processing errors: ' + str(len(image_error_list))
        print '   --------------------------------'
    elif args.refresh_nfos is True:
        print '   --------------------------------'
        print '   |  Updated nfos: ' + str(len(updated_nfos_lib))
        print '   --------------------------------'

    if args.show_status is True:
        if len(series_new_lib) > 0 or len(episode_new_lib) > 0 or len(special_new_lib) > 0:
            print ''
            print '   THESE LINKS ARE NOT YET CREATED:'
            print '   ----------------------------------'
            if len(series_new_lib) > 0:
                print '   New Series:'
                count = 1
                for s in series_new_lib:
                    print '   ' + str(count) + ' - ' + s
                    count += 1
                print ''
            if len(episode_new_lib) > 0:
                print '   New Episodes:'
                count = 1
                for s in episode_new_lib:
                    print '   ' + str(count) + ' - ' + s
                    count += 1
                print ''
            if len(special_new_lib) > 0:
                print '   New Specials:'
                count = 1
                for s in special_new_lib:
                    print '   ' + str(count) + ' - ' + s
                    count += 1
                print ''
        else:
            print ''
            print '   No new recordings were found.'

    elif len(image_error_list) > 0:
        print ''
        print ''
        print 'Warning: One or more banner, fanart, or poster images could not be created for these recordings:'
        print '-----------------------------------------------------------------------------------------------'
        for lf in image_error_list:
            print lf
    print ''

    encountered_image_error = (len(image_error_list) > 0)
    encountered_other_error = ('ERROR' in log_content)
    if encountered_image_error is True:
        print 'Encountered error processing poster, banner, or fanart image for new series.'
    elif encountered_other_error is True:
        print 'Encountered an error. Check log.'

    if encountered_image_error is True or encountered_other_error is True:
        return False
    else:
        # print 'Done! Completed successfully.'
        print ''
        return True


#try:
def main():
    success = True
    initialize_logging()
    if args.print_config is True:
        print_config()
    elif args.comskip_all is True:
        comskip_all()
    elif args.comskip_status is True:
        comskip_status()
    elif args.add_all is True or args.show_status is True or args.add_match_title is not None or args.add is not None or args.print_match_filename is not None or args.refresh_nfos is True or args.comskip is not None:
        success = read_recordings()
        if success is False:
            raise Exception('read_recordings() returned false')
        else:
            log.info('DONE! Completed successfully!')
            sys.exit(0)
    sys.exit(0)

if __name__ == '__main__':
    main()

#except: # catch *all* exceptions
   #e = sys.exc_info()[0]
   #print( "<p>Error: %s</p>" % e )
#except Exception, e:
    #print('Line number: ' + str(sys.exc_traceback.tb_lineno))
    #print('Exception message: ' + str(e))
    #print('Traceback: ' + sys.exc_info()[0])
    #sys.exit(1)





def new_series_from_tmdb(title, inetref, category, directory):
    """
    create a new show from a tmdb id
    :param title:
    :param inetref:
    :param category:
    :param directory:
    :return: True: success, False: error
    """
    global log
    api_url = 'http://api.themoviedb.org/3'
    headers = {'Accept': 'application/json'}

    request = urllib2.Request('{url}/configuration?api_key={key}'.format(url=api_url, key=config.tmdb_key),
                              headers=headers)
    cr = json.loads(urllib2.urlopen(request).read())

    # base url
    base_url = cr['images']['base_url']
    poster_sizes = cr['images']['poster_sizes']
    backdrop_sizes = cr['images']['backdrop_sizes']
    """
        'sizes' should be sorted in ascending order, so
            max_size = sizes[-1]
        should get the largest size as well.
    """

    def size_str_to_int(x):
        return float("inf") if x == 'original' else int(x[1:])

    # max_size
    max_poster_size = str(max(poster_sizes, key=size_str_to_int))
    max_backdrop_size = str(max(backdrop_sizes, key=size_str_to_int))

    series_id = get_series_id(inetref)
    request = urllib2.Request('{url}/movie/{id}?api_key={key}'.format(url=api_url, id=series_id, key=config.tmdb_key))
    mr = json.loads(urllib2.urlopen(request).read())

    # #### POSTER #####
    log.info('Getting path to poster...')
    poster_path = mr['poster_path']
    poster_url = '{0}{1}{2}'.format(base_url, max_poster_size, poster_path)
    if poster_path is None:
        return False
    poster_target = os.path.join(directory, 'poster.jpg')
    log.info('Downloading poster...')
    if download_file(poster_url, poster_target) is False:
        return False

    # #### FANART #####
    log.info('Getting path to fanart...')
    backdrop_path = mr['backdrop_path']
    backdrop_url = '{0}{1}{2}'.format(base_url, max_backdrop_size, backdrop_path)
    if backdrop_path is None:
        return False
    backdrop_target = os.path.join(directory, 'fanart.jpg')
    log.info('Downloading fanart...')
    if download_file(backdrop_url, backdrop_target) is False:
        return False

    # print '    poster_path: ' + poster_path
    # print '    backdrop_path: ' + backdrop_path

    # request = Request('{url}/movie/{id}/images?api_key={key}'.format(url=api_url, id=series_id, key=config.tmdb_key))
    # ir = json.loads(urlopen(request).read())

    # #### BANNER #####
    # make a 758 x 140 banner from poster
    log.info('Making 758 x 140 banner image from poster...')
    response = download_file(poster_url, '', True)
    if response is None or response is False:
        return False
    img = Image.open(cStringIO.StringIO(response.read()))
    # print 'w: ' + img.size[0] + ' h: ' + img.size[1]
    banner_ratio = 758 / float(140)
    # shift crop down by 200 pixels
    box = (0, 220, img.size[0], int(round((img.size[0] / banner_ratio))) + 220)
    img = img.crop(box).resize((758, 140), Image.ANTIALIAS)
    banner_file = os.path.join(directory, 'banner.jpg')
    log.info('Saving banner image file to ' + banner_file)
    img.save(banner_file)

    # print mr
    # print mr['title']
    # print mr['runtime']

    rating = unicode(mr['vote_average'])
    votes = unicode(mr['vote_count'])
    plot = unicode(mr['overview'])
    id = unicode(mr['id'])
    premiered = unicode(mr['release_date'])
    studio = ''
    date_added = ''

    # assemble genre string
    # print mr['genres']
    genres = mr['genres']
    if genres is not None:
        genre_list = ''
        for genre in genres:
            name = genre['name']
            if name is not None:
                if not name.lower() == category.lower():
                    genre_list += name + '|'
        if category is not None:
            genre_list += category
        genre_list = genre_list.strip('|')

    return True


