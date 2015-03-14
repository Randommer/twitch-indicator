#!/usr/bin/python

from gi.repository import Gtk as gtk
from gi.repository import Gio, GObject, Notify, GdkPixbuf, Gdk
from gi.repository import AppIndicator3 as appindicator
import os

import urllib
import json
import sys
import webbrowser
import threading

class Twitch:
  def fetch_followed_channels(self, username):
    """Fetch user followed channels and return a list with channel names."""
    try:
      self.followed_channels = []
      
      self.f = urllib.urlopen("https://api.twitch.tv/kraken/users/{0}/follows/channels?direction=DESC&limit=100&offset=0&sortby=created_at".format(username))
      self.data = json.loads(self.f.read())

      self.pages = (self.data['_total'] - 1) / 100
      for page in range(0, self.pages + 1):
        if page != 0:
          self.f = urllib.urlopen("https://api.twitch.tv/kraken/users/{0}/follows/channels?direction=DESC&limit=100&offset={1}&sortby=created_at".format(username, (page * 100)))
          self.data = json.loads(self.f.read())

        for channel in self.data['follows']:
          self.followed_channels.append(channel['channel']['display_name'])
      
      return self.followed_channels
    except IOError:
      return None

  def fetch_live_streams(self, channels):
    """Fetches live streams data from Twitch, and returns as list of dictionaries"""
    try:
      self.channels_count = len(channels)
      self.live_streams = []
      
      self.pages = (self.channels_count - 1) / 75
      for page in range(0, self.pages + 1):
        self.offset = (page * 75) + 75
        if (self.offset % 75 > 0):
          self.offset = self.channels_count 
        self.channels_offset = channels[(page * 75):self.offset]

        self.f = urllib.urlopen("https://api.twitch.tv/kraken/streams?channel={0}".format(','.join(self.channels_offset)))
        self.data = json.loads(self.f.read())

        for stream in self.data['streams']:
          # For some reason sometimes stream status and game is not present in
          # twitch API.
          try:
            self.status = stream['channel']['status']
          except KeyError:
            self.status = ""
          
          st = {
            'name': stream['channel']['display_name'],
            'status': self.status,
            'image': stream['channel']['logo'],
            'url': "http://www.twitch.tv/%s" % stream['channel']['name']
          }

          self.live_streams.append(st)
        return self.live_streams
    except IOError:
      return None

class Indicator():
  SETTINGS_KEY = "apps.twitch-indicator-applet"

  def __init__(self):
    # Setup applet icon depending on DE
    self.desktop_env = os.environ.get('DESKTOP_SESSION')
    if self.desktop_env == "pantheon":
      self.applet_icon = "indicator_elementary"
    else:
      self.applet_icon = "indicator_ubuntu"

    # Create applet
    self.a = appindicator.Indicator.new(
      'Twitch indicator applet',
      'wallch_indicator',
      appindicator.IndicatorCategory.APPLICATION_STATUS
    )
    self.a.set_status(appindicator.IndicatorStatus.ACTIVE)
    self.a.set_icon_theme_path("/usr/lib/twitch-indicator-applet/")
    self.a.set_icon(self.applet_icon)

    # Load settings
    self.settings = Gio.Settings.new(self.SETTINGS_KEY)

    # Setup menu
    self.menu = gtk.Menu()
    self.menuItems = [
      gtk.MenuItem('Check now'),
      gtk.SeparatorMenuItem(),
      gtk.MenuItem('Settings'),
      gtk.MenuItem('Quit')
    ]

    self.menuItems[0].connect('activate', self.refresh_streams_init)
    self.menuItems[-2].connect('activate', self.settings_dialog)
    self.menuItems[-1].connect('activate', self.quit)
    
    for i in self.menuItems:
      self.menu.append(i)

    self.a.set_menu(self.menu)
    
    self.menu.show_all()

  def refresh_menu(self, rebuild=False):
    """Rebuilds indicator menu."""
    if(rebuild):
      self.menuItems = [
        gtk.MenuItem('Check now'),
        gtk.SeparatorMenuItem(),
        gtk.MenuItem('Settings'),
        gtk.MenuItem('Quit')
      ]

      self.menuItems[0].connect('activate', self.refresh_streams_init)
      self.menuItems[-2].connect('activate', self.settings_dialog)
      self.menuItems[-1].connect('activate', self.quit)
      
    for i in self.menu.get_children():
      self.menu.remove(i)

    for i in self.menuItems:
      self.menu.append(i)

    self.menu.show_all()

  def open_link(self, widget, url):
    """Opens link in a default browser."""
    webbrowser.open_new_tab(url)

  def refresh_streams_init(self, widget):
    """Initializes thread for stream refreshing."""
    self.t = threading.Thread(target=self.refresh_streams, args=(widget))
    self.t.daemon = True
    self.t.start()

  def settings_dialog(self, widget):
    """Shows applet settings dialog."""
    self.dialog = gtk.Dialog(
      "Settings",
      None,
      0,
      (gtk.STOCK_CANCEL, gtk.ResponseType.CANCEL,
       gtk.STOCK_OK, gtk.ResponseType.OK)
    )

    self.table = gtk.Table(2, 2, False)

    self.username_label = gtk.Label("Twitch username")
    self.username_input = gtk.Entry()
    self.username_input.set_text(self.settings.get_string("twitch-username"))

    self.notifications_label = gtk.Label("Enable notifications")
    self.notifications_checkbox = gtk.Switch()
    self.notifications_checkbox.set_active(self.settings.get_boolean("enable-notifications"))

    self.table.attach(self.username_label, 0, 1, 0, 1, gtk.AttachOptions.FILL, gtk.AttachOptions.FILL, 6, 4)
    self.table.attach(self.username_input, 1, 2, 0, 1, gtk.AttachOptions.FILL, gtk.AttachOptions.FILL, 6, 4)
    self.table.attach(self.notifications_label, 0, 1, 1, 2, gtk.AttachOptions.FILL, gtk.AttachOptions.FILL, 6, 4)
    self.table.attach(self.notifications_checkbox, 1, 2, 1, 2, gtk.AttachOptions.EXPAND, gtk.AttachOptions.FILL, 6, 4)

    self.grid = gtk.Grid.new()
    self.grid.attach(self.table, 0, 0, 0, 0)

    self.username_label.show()
    self.username_input.show()
    self.notifications_label.show()
    self.notifications_checkbox.show()
    self.table.show()

    self.box = self.dialog.get_content_area()
    self.box.add(self.table)
    self.response = self.dialog.run()

    if self.response == gtk.ResponseType.OK:
      self.settings.set_string("twitch-username", self.username_input.get_text())
      self.settings.set_boolean("enable-notifications", self.notifications_checkbox.get_active())
    elif self.response == gtk.ResponseType.CANCEL:
      pass

    self.dialog.destroy()

  def refresh_streams(self, items):
    """Refreshes live streams list. Also pushes notifications when needed."""
    self.refresh_menu(True)

    # Disable check now button in menu and update text.
    self.menuItems[0].set_sensitive(False)
    self.menuItems[0].set_label("Checking...")
    self.refresh_menu()

    # Create twitch instance and fetch followed channels.
    self.tw = Twitch()
    self.followed_channels = self.tw.fetch_followed_channels(self.settings.get_string("twitch-username"))

    # If we can't retrieve channels, update menu accordingly.
    if self.followed_channels == None:
      self.menuItems.insert(2, gtk.MenuItem("Cannot retrieve channels"))
      self.menuItems.insert(3, gtk.SeparatorMenuItem())
      self.menuItems[2].set_sensitive(False)

      # Re-enable "Check now" button
      self.menuItems[0].set_sensitive(True)
      self.menuItems[0].set_label("Check now")
      self.refresh_menu()

      # Stop further execution.
      return

    # Fetch live streams
    self.live_streams = self.tw.fetch_live_streams(self.followed_channels)

    # If we can't retrieve streams, update menu accordingly.
    if self.live_streams == None:
      self.menuItems.insert(2, gtk.MenuItem("Cannot retrieve live streams"))
      self.menuItems.insert(3, gtk.SeparatorMenuItem())
      self.menuItems[2].set_sensitive(False)

      # Re-enable "Check now" button
      self.menuItems[0].set_sensitive(True)
      self.menuItems[0].set_label("Check now")
      self.refresh_menu()

      # Stop further execution.
      return

    # Update menu with live streams
    self.streams_menu = gtk.Menu() 
    self.menuItems.insert(2, gtk.MenuItem("Live channels ({0})".format(len(self.live_streams))))
    self.menuItems.insert(3, gtk.SeparatorMenuItem())
    self.menuItems[2].set_submenu(self.streams_menu)

    for index, stream in enumerate(self.live_streams):
      self.streams_menu.append(gtk.MenuItem(stream["name"]))
      self.streams_menu.get_children()[index].connect('activate', self.open_link, stream["url"])
    
    for i in self.streams_menu.get_children():
      i.show()
    
    # Re-enable "Check now" button
    self.menuItems[0].set_sensitive(True)
    self.menuItems[0].set_label("Check now")
    self.refresh_menu()

    # Push notifications of new streams
    if (self.settings.get_boolean("enable-notifications")):
      self.push_notifications(self.live_streams)

  def push_notifications(self, streams):
    """Pushes notifications of every stream, passed as a list of dictionaries."""
    try:
      for stream in streams:
        self.image = gtk.Image()
        self.response = urllib.urlopen(stream["image"])
        self.loader = GdkPixbuf.PixbufLoader.new()
        self.loader.write(self.response.read())
        self.loader.close()

        Notify.init("image")
        self.n = Notify.Notification.new("%s just went LIVE!" % stream["name"],
          stream["status"],
          "",
        )

        self.n.set_icon_from_pixbuf(self.loader.get_pixbuf())
        self.n.show()
    except IOError:
      return

  def main(self):
    """Main indicator function."""
    gtk.main()

  def quit(self, item):
    """Quits the applet."""
    gtk.main_quit()

if __name__=="__main__":
  Gdk.threads_init()
  gui = Indicator()
  gui.main()
