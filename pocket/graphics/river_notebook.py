"""Short, optional riverbank puzzles. Rule references are in field-companion.md."""
import textwrap

CARDS=(
 ('Two silver shapes hold still in the current. Where would you look for returning coho?',
  ('Downstream of Slippery Falls','Above the campground'),0,
  'A four-metre drop at Slippery Falls blocks the upriver run. Resident trout live up here.'),
 ('Your fly box clicks open by the park stream. Which pocket do you reach into?',
  ('The scented bait','The single barbless fly'),1,
  'Park streams allow artificial flies and lures with single-point barbless hooks. Choose lead-free tackle.'),
 ('A trout has a small fin between its back fin and tail. What is it?',
  ('Adipose fin','Second tail'),0,
  'On Washington Chinook and coho, a clipped adipose and healed scar identify a marked hatchery fish. Check the water, species and season before keeping a fish.'),
 ('The trail opens onto Tipsoo Lake. What comes out of your pack?',
  ('Fishing rod','Sketchbook'),1,
  'Tipsoo Lake is closed to fishing to protect its shores. A high lake can have different rules from its inlet.'),
 ('A bull trout slips into the net on an open park stream. What next?',
  ('Gently release it','Keep it for supper'),0,
  'Mount Rainier requires release of native stream fish. Bull trout have light spots and pale leading fin edges.'),
 ('Clear creek water, empty bottle. What goes on the camp stove?',
  ('Just an empty mug','Water for a rolling boil'),1,
  'Clear water can carry Giardia. CDC recommends a rolling boil for 1 minute, or 3 minutes above 6,500 feet.'),
 ('Two fish are working over a pale patch of gravel. Where do you settle?',
  ('Back on the bank to watch','Right on the gravel'),0,
  'That gravel may be a spawning nest. The park prohibits fishing for spawning fish.'),
 ('A November morning at the Ohanapecosh campground. What goes in your hand?',
  ('Binoculars','A fishing rod'),0,
  'The published park stream season here ends October 31. Check current NPS alerts before a real outing.'),
)


class RiverNotebook:
    def __init__(self):
        self.page=0
        self.answer=None
        self.score=0
        self.actions={}

    def lines(self,width):
        self.actions={}
        question,choices,correct,story=CARDS[self.page]
        rows=['River stones   '+str(self.score)+' / '+str(len(CARDS)),'']
        rows.extend(textwrap.wrap(question,max(15,width-2)))
        if self.answer is None:
            for i,choice in enumerate(choices):
                start=len(rows)
                rows.extend(('',*textwrap.wrap('[ '+choice+' ]',max(15,width-2)),''))
                self.actions.update((j,i) for j in range(start,len(rows)))
        else:
            rows.extend(('', 'A smooth river stone!' if correct==self.answer else 'A clue for next time.',''))
            rows.extend(textwrap.wrap(story,max(15,width-2)))
            start=len(rows)
            rows.extend(('','[ Next pebble ]' if self.page+1<len(CARDS) else '[ Finish ]',''))
            self.actions.update((j,2) for j in range(start,len(rows)))
        self.actions[len(rows)]=3
        return tuple(rows+['[ Back to the fox ]'])

    def tap(self,y):
        action=self.actions.get(y)
        if action==3:return False
        if action in (0,1) and self.answer is None:
            self.answer=action
            if action==CARDS[self.page][2]:self.score+=1
        elif action==2:
            self.page+=1;self.answer=None
            if self.page==len(CARDS):return False
        return True


PLANTS={
    'blueberry':('Blueberry shrub','Look for round blue berries among the leaves on the trail to the fox.'),
    'conifer':('Evergreen conifer','Step under the low branches and look up through the layers of needles.'),
    'fern':('Forest fern','Look down near the forest floor. Each spreading frond divides into smaller leaflets.'),
}


def record_plant(key):
    from data_paths import rainier_cache
    if key not in PLANTS:raise ValueError('Unknown plant')
    folder=rainier_cache()/'plants'
    folder.mkdir(parents=True,exist_ok=True)
    (folder/key).touch(exist_ok=True)


class DiscoveryBook:
    def __init__(self,view):
        from data_paths import rainier_cache
        from river_explore import photo_paths
        from wildlife_models import NAMES
        self.view=view
        self.photos=photo_paths()
        animals={p.stem.rsplit('-',1)[0] for p in self.photos}
        plants=rainier_cache()/'plants'
        self.entries=sorted([(NAMES[k],k,'[ See my photograph ]') for k in animals if k in NAMES]+
                            [(name,k,clue) for k,(name,clue) in PLANTS.items() if (plants/k).is_file()])
        self.page=0
        self.damaged=set()

    @property
    def preview(self):
        if not self.entries:return None
        key=self.entries[self.page][1]
        return next((p for p in self.photos if p not in self.damaged and p.stem.rsplit('-',1)[0]==key),None)

    def picture_rows(self):
        return max(0,self.view.host.window(self.view.name).h-11) if self.preview else 0

    def lines(self,width):
        if self.entries:
            name,key,clue=self.entries[self.page]
            heading=f'My guidebook   {self.page+1}/{len(self.entries)}'
            body=[name,*(['']*self.picture_rows()),*textwrap.wrap(clue,max(16,width-2))]
        else:
            heading='My guidebook'
            body=textwrap.wrap('Photograph an animal or walk up to a plant to fill your first page.',max(16,width-2))
        return tuple([heading,'',*body,'','[ Previous ]    [ Next ]','[ Photo album ]','[ Back to the river ]','for ella'])

    def tap_xy(self,x,y):
        height=len(self.lines(self.view.host.window(self.view.name).w-2))
        if self.entries and 3<=y<=3+self.picture_rows():
            key=self.entries[self.page][1]
            shots=[p for p in self.photos if p.stem.rsplit('-',1)[0]==key]
            if shots:
                self.view.album=shots
                self.view.album_index=0
                self.view.album_loaded=None
                return False
        if y==height-2:return False
        if y==height-3 and self.photos:
            self.view.album=self.photos.copy()
            self.view.album_index=0
            self.view.album_loaded=None
            return False
        if y==height-4 and self.entries:
            self.page=(self.page+(1 if x>=14 else -1))%len(self.entries)
        return True
