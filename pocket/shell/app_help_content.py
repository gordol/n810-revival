"""App-owned help for implemented controls and the evidence each view displays."""
PAGES={
    'Radio Feed':(
        ('Browse packets',('Up/Down or j/k selects a packet in the packet pane.','PageUp/PageDown, Home/End moves through the list.','/ starts list search; Enter accepts, Esc clears search.','n / N moves to the next / previous search match.','Tab / Shift-Tab switches packet and detail panes.','Enter opens the selected packet details.','Mouse wheel scrolls the pane under the pointer.')),
        ('Original evidence',('e toggles original bytes and diagnostic evidence.','i expands/restores the inspector; Esc restores both panes.','Up/Down or j/k scrolls focused details; PageUp/PageDown pages.','Shift-F10 opens actions for the selected record.','Right-click a record opens its actions.','Inspect record uses the original retained capture.','Host write evidence does not prove over-the-air delivery.')),
        ('Filters and pause',('f cycles all / received / transmitted records.','t reverses packet time order.','p or Space pauses this view; reception continues.','Resume catches up with the current retained snapshot.','Selection is preserved as new records arrive.','A filtered-out selection is identified in the status line.','Missing timestamps or original bytes remain unknown.')),
    ),
    'Services':(
        ('Discover services',('Focus the tab strip, then Left/Right changes the category.','Up/Down selects an entry in the discovery pane.','PageUp/PageDown, Home/End moves through the list.','/ searches; Enter accepts, Esc clears search.','n / N moves to the next / previous search match.','Tab / Shift-Tab moves focus between the tab strip and panes.','Enter focuses the selected entry details.','Click a category, pane or entry to select it.')),
        ('Read the evidence',('e toggles original packet and route evidence.','Up/Down or j/k scrolls focused details; PageUp/PageDown pages.','Home/End jumps to the start/end of the focused details.','Mouse wheel scrolls the pane under the pointer.','F5 requests a view update.','An advertisement is evidence, not a reachability test.','Retained packets may be old; missing dates stay unknown.')),
    ),
    'Messages':(
        ('Reticulum and MeshCore chat',('p selects APRS, Reticulum or MeshCore.','Choose its owner in Connections first; o connects.','Select a contact; v compares its full fingerprint before trust.','c composes; Ctrl-S sends explicitly; Enter does not send.','Esc leaves a draft; drafts remain separate for each owner/contact.','Reticulum a changes public discovery after confirmation.','MeshCore channels identify public or shared-key membership.','Sent means submitted; only an acknowledgement confirms delivery.','d disconnects the MeshCore radio.')),
        ('Conversations',('f switches my traffic / all heard traffic.','i shows my inbox; h shows all heard conversations.','Up/Down selects a conversation in the list.','/ searches; Enter accepts, Esc clears search.','n / N moves to the next / previous search match.','Tab / Shift-Tab moves focus between panes and actions.','Enter focuses the selected conversation.','Exact callsign SSIDs and protocols remain separate.')),
        ('Reading and drafts',('Up/Down or j/k scrolls the conversation; PageUp/PageDown pages.','Home/End jumps to the beginning/end of the conversation.','Mouse wheel scrolls the pane under the pointer.','c opens a scratchpad for an eligible APRS conversation.','Type to edit; cursor keys and Backspace edit the draft.','Esc leaves the scratchpad; Tab moves focus.','Enter does not transmit or save: this is a local draft.','BSS and other observed traffic are read only.')),
    ),
    'Stations':(
        ('Station directory',('Focus the station filter to type a callsign or name; / searches the list.','Backspace edits the filter; Esc clears it.','Up/Down and PageUp/PageDown selects list entries.','Tab moves focus between the list, details and filter.','Up/Down or j/k scrolls focused details; Home/End jumps to ends.','Mouse wheel scrolls the pane under the pointer.','Enter or v opens the selected station on the map.','U opens the selected callsign in offline ULS Lookup.','FCC identity also appears in the station details pane.','Mailing locality is separate from the received station position.')),
        ('Evidence and actions',('Click a list entry to select it in directory and map.','Shift-F10 opens actions for the selected station.','Right-click an entry opens the same station actions.','Advertised symbols and observed relay use are distinct.','A missing location or advertisement stays unknown.','Heard-through entries summarize retained observations.','This directory does not transmit radio packets.')),
    ),
    'Station Map':(
        ('Layers and internet fill',('S opens/closes the sidebar with locator, layers and details.','Inside the sidebar: L layers, D selected-item details.','Up/Down or the wheel scrolls sidebar controls below the locator.','Home/End jumps to the first/last sidebar controls.','N toggles station labels; P toggles repeater labels.','Markers stay selectable when labels are hidden.','The selected station and QTH remain labeled.','Click a station or repeater to inspect it in the sidebar.','On small screens the map opens to fill the work area.','T in the sidebar opens Station Map app settings.','Disable Terrain profiles, LOS and obstructions to stop and hide those tools.','R in Layers shows/hides coordinated repeater markers.','F in Layers opens station filters.','A sets your APRS call; C sets contact calls including SSIDs.','I starts/stops contact-only, receive-only APRS-IS fill.','Internet positions are marked I and expire from RAM after 30 minutes.','Only message/ACK evidence is retained, for 24 hours, separately from RF.','Repeater actions include details, QTH profile and Tune UV-Pro on B.','Tuning keeps APRS A/digital mapping; a matching or empty memory is used.','Restore previous radio selection restores an unchanged tuning session.')),
        ('Navigate the map',('Drag the map to pan.','Scroll over the map to zoom around the mouse pointer.','+ / - zooms around the map center.','Arrow keys pan the map.','a fits filtered stations with known positions.','f centers the selected station; F toggles following it.','Manual navigation pauses following.','d opens the station directory.')),
        ('Find and select stations',('g opens filters; / opens callsign/name search.','In filters: Up/Down chooses a category, Enter applies.','Tab switches category and query; c clears from category.','Esc returns from filters to the map.','l toggles the compact symbol legend.','Click a marker or label to select the shared station.','Repeated clicks cycle overlapping station targets.','Right-click or Shift-F10 opens station actions.')),
        ('Interpret symbols',('Gold identifies selection independently of symbol type.','Symbols are terminal approximations of APRS symbols.','Primary /, alternate \\ and overlay codes stay explicit.','A mobile symbol does not prove a station is moving.','Gateway/link symbols do not prove current reachability.','Unknown-position stations are counted but not plotted.','The catalog and labels are bounded for fast local use.')),
    ),
}


SPLIT_HELP=('Resize and focus panes',(
    'Drag the vertical divider to resize the two panes.',
    'Ctrl-R starts keyboard resizing outside search/draft editing.',
    'Left/Right adjusts the split one column at a time.',
    'Enter keeps the split; Esc restores its starting position.',
    'Pane minimum widths prevent either side collapsing.',
    'Tab moves focus between panes and controls; narrow windows reveal the focused pane.',
    'The focused pane has a highlighted heading.',
    'Pane ratio and focus are remembered with the desktop session.',
))


def pages(name):return PAGES[name]+((SPLIT_HELP,) if name!='Station Map' else ())
