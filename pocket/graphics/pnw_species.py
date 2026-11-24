"""Regional field-guide studies: body plan, approximate adult length in m, back, breast, field mark."""
from typing import NamedTuple


class Species(NamedTuple):
    name: str
    form: str
    length: float
    back: int
    belly: int
    mark: int


# Regional species use representative adult plumages and summer coats.
def catalog():
    rows = """
American crow|crow|.46|292d35|303238|434953
Common raven|raven|.63|252631|302b35|464553
Great horned owl|tufted owl|.55|78624d|c1a785|dcb65c
Barred owl|owl|.51|786b5c|dbd3bc|443c33
Northern spotted owl|owl|.44|665746|b59f82|eee4c7
Northern pygmy owl|owl|.17|856a50|d5c4aa|e4c764
Northern saw-whet owl|owl|.20|886c4a|cdad80|e0ae48
Western screech owl|tufted owl|.22|786f66|c0b9a8|d2b45b
Steller's jay|crested|.32|344571|354f93|242a36
Canada jay|songbird|.29|686e70|bbbdb6|eeeae0
Black-capped chickadee|tit|.13|93928a|dbcfb2|262623
Chestnut-backed chickadee|tit|.12|9a5f41|ccc3b4|3c3430
Mountain chickadee|tit|.14|888884|c1bba9|eeeae1
Red-breasted nuthatch|climber|.12|6a7c87|bf8867|252d33
Brown creeper|climber|.13|796855|dfd6c2|b9aa8a
Pacific wren|wren|.10|72543e|917157|554835
Bewick's wren|wren|.13|846a51|c3baab|e4dece
American robin|thrush|.25|626260|b66543|d7aa54
Varied thrush|thrush|.24|555f65|cd925f|393e42
Swainson's thrush|thrush|.18|80705b|d4c6a8|a58b69
Hermit thrush|thrush|.18|86735d|d7cab9|a16848
American dipper|dipper|.18|555d65|636a6d|bbbeb6
Belted kingfisher|kingfisher|.32|586d80|e5e2d6|64768a
Pileated woodpecker|woodpecker|.44|303130|393836|c23b30
Hairy woodpecker|woodpecker|.24|343432|e4e0d2|a83532
Downy woodpecker|woodpecker|.16|373935|e5e4db|b13335
Northern flicker|woodpecker|.32|908575|cbbaa4|ca6e49
Red-breasted sapsucker|woodpecker|.21|44413e|b8ab80|aa3937
Rufous hummingbird|hummer|.085|b87142|c89168|c44d2b
Anna's hummingbird|hummer|.10|667d55|aaa99a|b04e72
Mallard|duck|.59|84776c|b8afa2|356951
Harlequin duck|duck|.42|546578|6a7580|faf4df
Common merganser|merganser|.62|343c40|e4dece|3b5856
Great blue heron|heron|1.12|788794|b7bdbe|d1ad69
Spotted sandpiper|wader|.19|80796a|e2d9c2|b5a174
Killdeer|wader|.25|947d65|ede6ce|352f2b
Dark-eyed junco|finch|.15|765e51|c7c4ba|4a4b4a
Pine siskin|finch|.13|827960|c6bca0|cfa94e
Western tanager|songbird|.18|474747|dbc34c|cb7143
Black-headed grosbeak|finch|.18|383b36|c98e58|2b302c
Yellow-rumped warbler|songbird|.14|737d83|d3cfbd|e9c84d
Bull trout|char|.60|636c59|b8aea0|ce9c83
Brook trout|char|.34|52694f|c49d71|ce745c
Coastal cutthroat trout|trout|.38|78856b|d1cab2|bc654b
Coho salmon|salmon|.71|56716e|bec9c7|434b4a
Chinook salmon|salmon|.90|535f63|bdc3bc|373a3a
Mountain whitefish|whitefish|.31|7c8278|c7c9b8|9e9f8c
Coastrange sculpin|sculpin|.10|716956|a0977d|494838
Western terrestrial garter snake|snake|.77|656451|b4afa0|c3bd88
Common garter snake|snake|.75|40463b|9a9e7e|d4be72
Northwestern garter snake|snake|.52|4c4e40|aea188|c98c54
Northern alligator lizard|lizard|.20|8b8067|c4bba2|584f43
Western fence lizard|lizard|.17|827761|a7a18e|55739a
Western skink|skink|.17|806d50|c6beab|bca979
Pacific treefrog|frog|.045|649252|c4c6a0|443f34
Cascades frog|frog|.07|827b4e|d2bf85|4a4639
Northern red-legged frog|frog|.08|927765|ba967b|ad6759
Coastal tailed frog|frog|.043|756e5b|c1b190|494a3f
Western toad|toad|.10|877e65|b0a88d|c6b694
Rough-skinned newt|newt|.16|685842|cb8a4b|473e30
Northwestern salamander|newt|.18|554d45|857a70|595451
Ensatina|newt|.12|966c50|ba986f|bc845a
Western red-backed salamander|newt|.09|584c41|989083|a36649
Long-toed salamander|newt|.14|48473f|858577|c1ae61
Columbia black-tailed deer|deer|1.48|987a5d|c9b497|473e34
Roosevelt elk|elk|2.35|9d8061|b5a38b|574639
Snowshoe hare|hare|.46|967c61|d8cec0|514a41
American beaver|beaver|.98|6b503d|8f7356|473f35
North American river otter|otter|1.05|62503f|9a8470|564939
American mink|weasel|.55|503d31|725847|ded0ba
Long-tailed weasel|weasel|.35|936b47|d7c49d|43382f
Raccoon|raccoon|.78|827b71|aba396|343436
Striped skunk|skunk|.69|343331|47453d|e2ddd1
Deer mouse|mouse|.17|9a8061|ddd3ba|bba188
Bushy-tailed woodrat|mouse|.34|91816b|cec7b4|827669
Townsend's vole|vole|.17|7c6b59|a49b8a|665d52
Big brown bat|bat|.13|735443|917963|463e39
Little brown myotis|bat|.09|715e4a|9b8971|50443b
Western tiger swallowtail|swallowtail|.10|d5bd55|c5b969|30332d
Pale swallowtail|swallowtail|.09|e4dec4|c1bfae|343833
Mourning cloak|butterfly|.07|633d38|5d5149|dfca86
Lorquin's admiral|butterfly|.065|413d35|73614d|eee6ce
Red admiral|butterfly|.06|383536|645646|d56845
Painted lady|butterfly|.06|cc895c|baa388|42382e
Cabbage white|butterfly|.05|ebe7cc|d8d9ac|595b50
Common green darner|dragonfly|.077|66936c|668eaa|3a4947
Eight-spotted skimmer|dragonfly|.048|545248|a7a491|35322e
Paddle-tailed darner|dragonfly|.074|50594e|7099a6|404a45
Yellow-faced bumble bee|bee|.018|d6b54e|3c3931|cca94b
Black-tailed bumble bee|bee|.019|be9d4a|454033|ad6746
Western honey bee|bee|.014|b18a42|8c693a|413b32
Spotted tussock moth|moth|.043|c69643|aa8752|685a48
Pacific banana slug|slug|.18|b8ac59|c1b56b|766f49
"""
    result={}
    for row in rows.strip().splitlines():
        name,form,length,*colors=row.split('|')
        key=name.lower().replace("'",'').replace(' ','_').replace('-','_')
        result[key]=Species(name,form,float(length),*(int(c,16) for c in colors))
    return result


REGIONAL=catalog()
BIRDS=set('crow raven crested songbird tit climber wren thrush dipper kingfisher woodpecker hummer duck merganser heron wader finch owl'.split())|{'tufted owl'}
FISH={'char','trout','salmon','whitefish','sculpin'}
HERPS={'snake','lizard','skink','frog','toad','newt'}
INVERTEBRATES={'swallowtail','butterfly','dragonfly','bee','moth','slug'}


def group(form):
    for name,forms in (('Birds',BIRDS),('Fish',FISH),('Herps',HERPS),('Invertebrates',INVERTEBRATES)):
        if form in forms:return name
    return 'Mammals'
