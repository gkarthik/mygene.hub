from mongokit import OR
from entrez_base import Gene2ECParser

__metadata__ = {
    '__collection__' : 'entrez_ec',
    'structure': {'ec': OR(unicode, list)},
}

def load_genedoc(self):
    gene2ec = Gene2ECParser().load()
    return gene2ec

def get_mapping(self):
    mapping = {
    	#do not index ec
        "ec": {"index": "no",
               "type": "string",
               "include_in_all": False},
    }
    return mapping
