import irclib
import collections
import signal
import string
import shelve
import re
import struct
import os
import sys
import time
import zipfile
import config
from pprint import pformat
import subprocess

irclib.DEBUG = True


class dccBot(irclib.SimpleIRCClient):
    def __init__(self):
        irclib.SimpleIRCClient.__init__(self)
        self.persist = shelve.open('list_of_requested.db', writeback=True)
        self.last_request = 0
        self.waiting = {}
        self.seen = {}
        self.received = {}
        self.receiving = True
        self.file_list = {}
        self.private = open('private_msgs.txt', 'a')
        if 'requested' in self.persist:
            self.requested = self.persist['requested']
        else:
            self.requested = {}
        print "Loaded {} old requested items".format(len(self.requested))
        self.motd_counter = 0
        self.music_files = []
        self.skip_song_votes = []
        self.player = None
        self.queue = collections.deque()

    def on_privnotice(self, connection, event):
        if event.source():
            print '\t:: ' + event.source() + ' ->' + event.arguments()[0]
        else:
            print event.arguments()[0]

        if(event.arguments()[0].find('I have added') >= 0 or
                event.arguments()[0].find('After waiting') >= 0):
            return

        self.private.write("{}\n".format(event.arguments()[0]))
        self.private.flush()

    def leave_handler(self, event):
        source = event.source().split('!')[0]
        self.connection.privmsg(source, 'Bye')
        self.connection.close()

    def refresh_handler(self, event):
        for root, subfolders, files in os.walk(config.root_dir):
            for file in files:
                filename = os.path.join(root, file)
                self.music_files.append(filename)

    def ls_handler(self, event):
        source = event.source().split('!')[0]
        if len(self.music_files) > 0:
            search_term = ' '.join(event.arguments()[0].split(' ')[1:])
            print search_term
            if len(search_term) > 0:
                for line in self.music_files:
                    if line.find(search_term) > -1:
                        self.connection.privmsg(source, os.path.basename(line))
                        time.sleep(1)
            else:
                self.connection.privmsg(source, 'Syntax: .ls <search term>')
        else:
            self.connection.privmsg(source, 'List empty')

    def find_first_result(self, search_term):
        for line in self.music_files:
            if line.find(search_term) > -1:
                return line

    def enqueue_handler(self, event):
        source = event.source().split('!')[0]
        item_to_queue = ' '.join(event.arguments()[0].split(' ')[1:])
        if len(item_to_queue) > 0:
            if len(self.music_files) > 0:
                filepath = self.find_first_result(item_to_queue)
                self.play(filepath)
            else:
                self.connection.privmsg(source, 'The list is empty. Try a refresh')
        else:
            self.show_queue_handler(event)

    #Random item queuing

    def show_queue_handler(self, event):
        source = event.source().split('!')[0]
        if len(self.queue) > 0:
            ctr = 0
            for item in self.queue:
                ctr += 1
                self.connection.privmsg(source, "{}:{}".format(ctr, os.path.basename(item)))
        else:
            self.connection.privmsg(source, 'The queue is empty. Better act fast!')

    def play(self, filepath):
        if not self.player or self.player.returncode:
            if filepath in self.music_files:
                if os.path.isfile(filepath):
                    self.skip_song_votes = []
                    self.player = subprocess.Popen([config.player, filepath])
            else:
                print self.music_files
                print filepath
                for _ in range(1, 9):
                    print "SOMETHING VERY BAD HAPPENED"
                    print filepath
        else:
            #something is playing TODO queue for next play
            self.queue.append(filepath)

    def next_handler(self, event):
        #Add this person to the list of people wanting to skip this song
        source = event.source().split('!')[0]
        self.skip_song_votes.append(source)
        #TODO Use a system of majority to skip a currently playing song

    def stop_handler(self, event):
        self.player.send_signal(signal.SIGTERM)

    def continue_handler(self, event):
        print self.player
        print self.player.returncode
        self.play(self.queue.pop())

    def help_handler(self, event):
        source = event.source().split('!')[0]
        self.connection.privmsg(source, '.h, .leave, .ls, .refresh, .q, .queue, .n, .s, .c')

    def on_privmsg(self, connection, event):
        source = event.source().split('!')[0]
        print source + ': ' + event.arguments()[0]

        command_mappings = {
                '.h': self.help_handler,
                '.leave': self.leave_handler,
                '.ls': self.ls_handler,
                '.refresh': self.refresh_handler,
                '.q': self.enqueue_handler,
                '.queue': self.enqueue_handler,
                '.n': self.next_handler,
                '.s': self.stop_handler,
                '.c': self.continue_handler,
                }

        if source in config.admin and event.arguments()[0].startswith('.'):
            command = event.arguments()[0].split(' ')[0]
            if command in command_mappings:
                command_mappings[command](event)
            else:
                message = "We are waiting to retrieve these:\n{}".format(
                    pformat(self.waiting))
                print message
                connection.privmsg(source, "{} Waiting".format(len(self.waiting)))
                message = "List of requests:\n{}".format(pformat(self.requested))
                print message
                connection.privmsg(source, "{} Requested".format(
                    len(self.requested)))
                min_val = time.time()
                next_key = None
                next_item = None
                for key in self.requested:
                    if self.requested[key]['date'] < min_val:
                        next_item = self.requested[key]
                        next_key = key
                        min_val = self.requested[key]['date']
                print next_item
                time_until_next_item = config.EXPIRE - (
                        time.time() - next_item['date'])
                message = "The next item: {} in {} s".format(
                        pformat({next_key: next_item}), time_until_next_item)
                connection.privmsg(source, message)
        else:
            print event.arguments()[0].startswith('.')
            print config.admin
            print source
            self.private.write("{}\n".format(event.arguments()[0]))
            self.private.flush()

    def on_pubmsg(self, connection, event):
        line = event.arguments()[0]
        list_position = line.lower().find('list')

        if line.startswith('.'):
            if event.arguments()[0] == '.motd':
                if config.motd and self.motd_counter == 0:
                    message = subprocess.Popen('/usr/games/fortune',
                            stdout=subprocess.PIPE).communicate()
                    source = event.target()
                    connection.privmsg(
                            source, "{}".format(
                                str(message[0]).replace('\n', ' ')))
                    self.motd_counter = (
                            (self.motd_counter + 1) % config.MOTD_FREQUENCY)
        else:
            if list_position > -1:
                for word in line.split():
                    if '@' in word:
                        word = filter(
                                lambda x: x in string.letters or x in ['@'],
                                word)
                        if(word.startswith("@")
                                and word not in config.blacklist):
                            # if we have not seen this trigger before add it to
                            # our list
                            if word not in self.seen:
                                self.seen.update(self.make_entry(event, word))
                                # if we have not requested this trigger before,
                                # and enough time has elapsed since the last
                                # request, or the last request is too far back,
                                # request it
                                if self.may_trigger_next(word):
                                    self.last_request = time.time()
                                    print "Sending trigger '{}' to '{}'".\
                                            format(word, event.target())
                                    connection.privmsg(event.target(), word)
                                    self.requested.update(
                                            self.make_entry(event, word))
                                    self.persist['requested'] = self.requested
                                    self.persist.sync()
                                else:
                                    self.waiting.update(self.make_entry(event, word))
                                    print "\tQueing trigger {}: {}".format(word, self.waiting)
                        else:
                            unmatched_word = open('unmatched.txt', 'a')
                            unmatched_word.write("{}\n".format(word))
                            unmatched_word.close()
                    else:
                        if 'shutup' in word or 'shaddap' in word:
                            print "sending sock to {}".format(event.target())
                            connection.privmsg(
                                    event.target(), "Yes, put a sock in it!")

            else:
                # print "not list advert, waiting has length of {}".format(len(self.waiting))
                # print time.time() - self.last_request - HAMMER_TIME
                if self.may_trigger_next():  # Test for hammer time
                    # print self.waiting
                    if len(self.waiting) > 0:
                        entry = self.waiting.popitem()
                        # print entry
                        # print(entry[1]['target'], entry[0])
                        if self.may_trigger_next(entry[0]):  # Test for expiry
                            print "Sending trigger '{}' to '{}'".format(entry[0],
                                entry[1])
                            connection.privmsg(entry[1]['target'], entry[0])
                            self.last_request = time.time()
                            self.requested[entry[0]] = entry[1]
                            # print self.waiting
                            #Update all waiting entries with new timestamps
                            # for entry in self.waiting.keys():
                            #     self.waiting[entry]['date'] = time.time()
                            # print self.waiting
                            self.persist['requested'] = self.requested
                            self.persist.sync()
                            # print "Persisted request {}".format(self.requested)
                #print event.target() + '> ' + event.source().split('!')[0] + ': ' + event.arguments()[0]

    def may_trigger_next(self, word=None):
        not_hammering = time.time() - self.last_request > config.HAMMER_TIME
        if word is not None:
            expired = word not in self.requested\
                or time.time() - self.last_request > config.EXPIRE
        else:
            expired = True
        return not_hammering and expired

    def make_entry(self, event, trigger):
        return {
            trigger: {
                'target': event.target(),
                'date': time.time(),
                }
            }

    def on_ctcp(self, connection, event):
        if len(event.arguments()) < 2:
            return
        args = event.arguments()[1].split()
        if args[0] != "SEND":
            return
        print "\tCTCP ", event.source(), event.arguments()
        filename = os.path.basename(" ".join(args[1:-3]))
        # print "Receiving {} from {}".format(filename, event.source().split('!')[0])
        if os.path.exists(filename):
            print "\tA file named", filename, "already exists. Renaming it."
            newname = filename
            counter = 0
            while os.path.exists(newname):
                postfix = re.search(r'(\d+)(\.?.{3})?$', newname)
                counter = counter + 1
                if postfix:
                    newname = newname.replace(postfix.group(1),
                        str(int(postfix.group(1)) + 1))
                else:
                    extention = re.search(r'\..{3}$', newname)
                    if extention:
                        newname = newname.replace(extention.group(),
                            "_{}{}".format(counter, extention.group()))
                    else:
                        newname = newname + "_{}".format(counter)
            os.rename(filename, newname)
        peeraddress = irclib.ip_numstr_to_quad(args[-3])
        peerport = int(args[-2])
        dcc = self.dcc_connect(peeraddress, peerport, "raw")
        # print "New DCC connection to {}:{} at {}".format(peeraddress, port, dcc)
        if peeraddress not in self.file_list:
            file_obj = open(filename, "wb")
            self.file_list[peeraddress] = {
                    'filename': filename, 'file': file_obj, 'connection': dcc,
                    'received_bytes': 0}

    def on_dcc_disconnect(self, connection, event):
        # print event.target(), event.source()
        print "Received file %s (%d bytes)." % (
                self.file_list[event.source()]['filename'],
                self.file_list[event.source()]['received_bytes'])
        self.file_list[event.source()]['file'].close()
        # print "Closed file {}".format(self.file_list[event.source()]['file'])
        # print "Closing connection at {}".format(
        #         self.file_list[event.source()]['connection'])
        self.file_list[event.source()]['connection'].disconnect()
        # print "Connection: {}".format(
        #         self.file_list[event.source()]['connection']._get_socket())
        if self.file_list[event.source()]['filename'].find('.zip') > -1:
            print "\tChecking file consistancy"
            compressed_file = zipfile.ZipFile(
                    self.file_list[event.source()]['filename'], 'r')
            if compressed_file.testzip() is None:
                print "\tFile is good"
            else:
                print "File is bad"
        del self.file_list[event.source()]

    def on_dccmsg(self, connection, event):
        # print event.target(), event.source()
        # print "Packet from {} on conn {}".format(event.source(), connection)
        data = event.arguments()[0]
        self.file_list[event.source()]['file'].write(data)
        self.file_list[event.source()]['received_bytes'] += len(data)
        # print "Wrote {} bytes to {}, and ack'd {} bytes".format(
        #         self.file_list[event.source()]['received_bytes'],
        #         self.file_list[event.source()]['filename'],
        #         len(data)
        #         )
        self.file_list[event.source()]['connection'].privmsg(
                struct.pack("!I",
                    self.file_list[event.source()]['received_bytes']))

    def on_endofmotd(self, connection, event):
        self.ircobj.connections[0].join(config.channel)

    def on_quit(self, connection, event):
        # self.private.close()
        pass

    def on_disconnect(self, connection, event):
        # self.private.close()
        pass


def main():
    connection = dccBot()
    try:
        connection.connect(config.network, config.port, config.nick)
    except irclib.ServerConnectionError,  x:
        print x
        sys.exit(1)
    connection.start()

if __name__ == "__main__":
    main()
