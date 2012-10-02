=======
listbot
=======

IRC list bot
A Python IRC bot intended for list serv channels. It monitors the list of
channels for list adverts, and collects the lists.

This is intended for gathering lists, and eventually queueing items from the
lists

Currently gathers lists, and functions as a jukebox on the machine its on.

Next steps:
* unpack lists
* provide a 'search' function for admin users
* provide a 'queue' function for admin users
* find and trigger items from the queue list
* skip tracks based on voting

Fixme
* Drop 'seen' list and just use 'waiting' and 'requested' so we can refresh
  files that expired
