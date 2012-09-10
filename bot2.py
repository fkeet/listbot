import irclib
import shelve
import re
import struct
import os
import sys
import time
import zipfile

# Connection information
# network = 'irc.servercentral.net'
# network = 'irc.paraphysics.net'
# network = 'eu.undernet.org'
# network = 'Hollywood.CA.US.Undernet.org'
network = '208.64.123.210'
port = 6667
channel = '#bookz'
# channel = '#magpietest'
nick = 'magpie'
name = 'magpie'
HAMMER_TIME = 20
EXPIRE = 60 * 1 * 1  # 15 day cache time
admin = ['fred__', 'cabel']
blacklist = ['@seach', '@seek', '@search/@seek']

# irclib.DEBUG = True


class dccBot(irclib.SimpleIRCClient):
    def __init__(self):
        irclib.SimpleIRCClient.__init__(self)
        self.persist = shelve.open('list_of_requested.db', writeback=True)
        self.last_request = 0
        self.waiting = {}
        self.seen = {}
        if 'requested' in self.persist:
            self.requested = self.persist['requested']
        else:
            self.requested = {}
        self.received = {}
        self.receiving = True
        self.file_list = {}
        self.private = open('private_msgs.txt', 'a')

    def on_privnotice(self, connection, event):
        if event.source():
            print '\t:: ' + event.source() + ' ->' + event.arguments()[0]
        else:
            print event.arguments()[0]
        self.private.write("{}\n".format(event.arguments()[0]))
        self.private.flush()

    def on_privmsg(self, connection, event):
        print event.source().split('!')[0] + ': ' + event.arguments()[0]

        if event.target() in admin and event.arguments()[0].startswith('.'):
            connection.privmsg(event.target(),
                "We are waiting to retrieve these:")
            message = "{}".format(self.waiting)
            connection.privmsg(event.target(), message)
        if event.arguments()[0].lower().find('hello') == 0:
            connection.privmsg(event.source().split('!')[0], 'Hello.')

    def on_pubmsg(self, connection, event):
        line = event.arguments()[0]
        list_position = line.lower().find('list')
        if list_position > -1:
            # print 'found list word'
            for word in line.split():
                if word.startswith("@") and word not in blacklist:
                    # print 'found trigger word'
                    #if we have not seen this trigger before add it to our list
                    if word not in self.seen:
                        self.seen.update(self.make_entry(event, word))
                        #if we have not requested this trigger before, and
                        #enough time has elapsed since the last request, or the
                        # last request is too far back, request it
                        if self.may_trigger_next(word):
                            # if word in self.requested:
                                # print "Last update {}".\
                                #         format(time.time() - EXPIRE
                                #         - self.requested[word]['date'])
                            self.last_request = time.time()
                            print "Sending trigger '{}' to '{}'".format(word,
                                event.target())
                            connection.privmsg(event.target(), word)
                            self.requested.update(self.make_entry(event, word))
                            self.persist['requested'] = self.requested
                            self.persist.sync()
                            # print "Persisted request {}".format(self.requested)
                        else:
                            # print time.time()-self.last_request > HAMMER_TIME
                            # print word not in self.requested
                            # if word in self.requested:
                            #     print(time.time() - EXPIRE - self.requested[word]['date'])
                            self.waiting.update(self.make_entry(event, word))
                            print "\tQueing trigger {}: {}".format(word, self.waiting)
                            # print self.waiting
                    # else:
                    #     print "but i've seen it before"
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
        not_hammering = time.time() - self.last_request > HAMMER_TIME
        if word is not None:
            expired = word not in self.requested\
                or time.time() - self.last_request > EXPIRE
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
        self.ircobj.connections[0].join(channel)

    def on_quit(self, connection, event):
        # self.private.close()
        pass

    def on_disconnect(self, connection, event):
        # self.private.close()
        pass


def main():
    connection = dccBot()
    try:
        connection.connect(network, port, nick)
    except irclib.ServerConnectionError,  x:
        print x
        sys.exit(1)
    connection.start()

if __name__ == "__main__":
    main()
