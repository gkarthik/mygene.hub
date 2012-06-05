import os.path
from config import species_li, taxid_d, DATA_FOLDER
from utils.common import , file_newer, loadobj, dump
from utils.dataload import (load_start, load_done,
                            tab2dict, tab2list, value_convert, normalized_value,
                            dict_convert, dict_to_list,
                            )

class EntrezParserBase(object):
    def __init__(self):
        self.species_li = species_li
        self.taxid_set = set([taxid_d[species] for species in species_li])
        self.DATA_FOLDER = DATA_FOLDER
        self.datafile = os.path.join(self.DATA_FOLDER, self.DATAFILE)

    def load(self, aslist=False):
        raise NotImplementedError


class GeneInfoParser(EntrezParserBase):
    '''Parser for NCBI gene_info.gz file.'''
    DATAFILE = 'gene/gene_info.gz'

    def load(self, aslist=False):
        '''
        loading ncbi "gene_info" file
        This must be called first to create basic gene documents
        with all basic fields, e.g., name, symbol, synonyms, etc.

        format of gene_info file:
        #Format: tax_id GeneID Symbol LocusTag Synonyms dbXrefs chromosome map_location description type_of_gene Symbol_from
        _nomenclature_authority Full_name_from_nomenclature_authority Nomenclature_status Other_designations Modification_da
        te (tab is used as a separator, pound sign - start of a comment)

        '''
        load_start(self.datafile)
        gene_d = tab2dict(self.datafile, (0,1,2,4,5,7,8,9), key=1, alwayslist=0, includefn=lambda ld:int(ld[0]) in self.taxid_set)
        def _ff(d):
            (taxid, symbol, synonyms,
            dbxrefs,map_location,
            description, type_of_gene) = d
            out = dict(taxid=int(taxid),
                       symbol = symbol,
                       name=description)
            if map_location != '-':
                out['map_location']=map_location
            if type_of_gene != '-':
                out['type_of_gene']=type_of_gene
            if synonyms != '-':
               out['alias']=normalized_value(synonyms.split('|'))

            for x in dbxrefs.split('|'):
                if x=='-': continue
                try:
                    _db, _id = x.split(':')
                except:
                    print x
                    raise
                if _db.lower() in ['ensembl', 'imgt/gene-db']:      # we don't need ensembl xref from here, we will get it from Ensembl directly
                    continue                                        # we don't need 'IMGT/GENE-DB" xref either, because they are mostly the same as gene symbol
                if _db.lower() == 'mgi':            # add "MGI:" prefix for MGI ids.
                    _id = "MGI:"+_id
                out[_db] = _id
            return out

        gene_d = value_convert(gene_d, _ff)

        #add entrezgene field
        for geneid in gene_d:
            d = gene_d[geneid]
            d['entrezgene'] = int(geneid)
            gene_d[geneid] = d

        load_done('[%d]' % len(gene_d))

        if aslist:
            return dict_to_list(gene_d)
        else:
            return gene_d



def get_geneid_d(species_li, load_cache=True, save_cache=True):
    '''return a dictionary of current/retired geneid to current geneid mapping.
       This is useful, when other annotations were mapped to geneids may contain
       retired gene ids.

       Note that all ids are int type.
    '''
    taxid_set = set([taxid_d[species] for species in species_li])
    orig_cwd = os.getcwd()
    os.chdir(DATA_FOLDER)

    #check cache file
    _cache_file = 'gene/geneid_d.pyobj'
    if load_cache and os.path.exists(_cache_file) and \
       file_newer(_cache_file, 'gene/gene_info.gz') and \
       file_newer(_cache_file, 'gene/gene_history.gz'):

        print 'Loading "geneid_d" from cache file...',
        _taxid_set, out_d = loadobj(_cache_file)
        assert _taxid_set == taxid_set
        print 'Done.'
        os.chdir(orig_cwd)
        return out_d

    DATAFILE = os.path.join(DATA_FOLDER, 'gene/gene_info.gz')
    load_start(DATAFILE)
    geneid_li = set(tab2list(DATAFILE, 1, includefn=lambda ld:int(ld[0]) in taxid_set))
    load_done('[%d]' % len(geneid_li))

    DATAFILE = os.path.join(DATA_FOLDER, 'gene/gene_history.gz')
    load_start(DATAFILE)
    retired2gene = tab2dict(DATAFILE, (1,2), 1, alwayslist=0, includefn=lambda ld:int(ld[0]) in taxid_set and ld[1] in geneid_li)
    # includefn above makes sure taxid is for species_li and filters out those mapped_to geneid exists in gene_info list

    load_done('[%d]' % len(retired2gene))

    out_d = dict_convert(retired2gene, keyfn=int, valuefn=int)    # convert key/value to int
    for g in geneid_li:
        _g = int(g)
        out_d[_g] = _g

    if save_cache:
        dump((taxid_set, out_d), _cache_file)

    os.chdir(orig_cwd)
    return out_d


class HomologeneParser(EntrezParserBase):
    '''Parser for NCBI homologenes.data file.'''
    DATAFILE = 'Homologene/homologene.data'

    def _sorted_homologenes(self, homologenes):
        '''sort list of homologenes [(taxid, geneid),...] based on the order
            defined in species_li.
        '''
        d = {}
        for i, species in enumerate(species_li):
            d[taxid_d[species]] = i
        gene_li = [(d[taxid], taxid, geneid) for taxid, geneid in homologenes]
        return [g[1:] for g in sorted(gene_li)]

    def load(self, aslist=False):
        '''
        loading ncbi "homologene.data" file
        adding "homologene" field in gene doc
        '''
        taxid_set = set([taxid_d[species] for species in self.species_li])
        load_start(self.datafile)
        with file(self.datafile) as df:
            homologene_d = {}
            doc_li = []
            print
            geneid_d = get_geneid_d(species_li)

            for line in df:
                ld=line.strip().split('\t')
                hm_id, tax_id, geneid = [int(x) for x in ld[:3]]
                if tax_id in taxid_set and geneid in geneid_d:
                    #for selected species only
                    #and also ignore those geneid does not match any existing gene doc
                    geneid = geneid_d[geneid]   # in case of orignal geneid is retired, replaced with the new one, if available.
                    genes = homologene_d.get(hm_id, [])
                    genes.append((tax_id, geneid))
                    homologene_d[hm_id] = genes

                    doc_li.append(dict(_id=str(geneid), taxid=tax_id, homologene={'id': hm_id}) )

            for i, gdoc in enumerate(doc_li):
                gdoc['homologene']['genes']=self._sorted_homologenes(set(homologene_d[gdoc['homologene']['id']]))
                doc_li[i] = gdoc

            load_done('[%d]' % len(doc_li))

        if aslist:
            return doc_li
        else:
            gene_d = dict([(d['_id'], d) for d in doc_li])
            return gene_d

class GeneSummaryParser(EntrezParserBase):
    '''Parser for gene2summary_all.txt, adding "summary" field in gene doc'''
    DATAFILE = 'refseq/gene2summary_all.txt'

    def load(self, aslist=False):
        load_start(self.datafile)
        with file(self.datafile) as df:
            geneid_set = set()
            doc_li = []
            for line in df:
                geneid, summary = line.strip().split('\t')
                if geneid not in geneid_set:
                    doc_li.append(dict(_id=geneid, summary=unicode(summary)))
                    geneid_set.add(geneid)
        load_done('[%d]' % len(doc_li))

        if aslist:
            return doc_li
        else:
            gene_d = dict([(d['_id'], d) for d in doc_li])
            return gene_d


class Gene2AccessionParserBase(EntrezParserBase):
    DATAFILE = 'to_be_specified'
    fieldname = 'to_be_specified'

    def load(self, aslist=False):
        load_start(self.datafile)
        gene2acc = tab2dict(self.datafile, (1,3,5,7), 0, alwayslist=1,
                            includefn=lambda ld:int(ld[0]) in self.taxid_set)
        def _ff(d):
            out = {'rna':[],
                   'protein':[],
                   'genomic':[]}
            for x1,x2,x3 in d:
                if x1!='-':
                    out['rna'].append(x1.split('.')[0])   #trim version number after dot
                if x2!='-':
                    out['protein'].append(x2.split('.')[0])
                if x3!='-':
                    out['genomic'].append(x3.split('.')[0])
            #remove dup
            for k in out:
                out[k] = normalized_value(out[k])
            #remove empty rna/protein/genomic field
            _out = {}
            for k,v in out.items():
                if v: _out[k] = v
            if _out:
                _out = {self.fieldname:_out}
            return _out

        gene2acc = dict_convert(gene2acc, valuefn=_ff)
        load_done('[%d]' % len(gene2acc))

        if aslist:
            return dict_to_list(gene2acc)
        else:
            return gene2acc

class Gene2AccessionParser(Gene2AccessionParserBase):
    DATAFILE = 'gene/gene2accession.gz'
    fieldname = 'accession'

class Gene2RefseqParser(Gene2AccessionParserBase):
    DATAFILE = 'gene/gene2refseq.gz'
    fieldname = 'refseq'


class Gene2UnigeneParser(EntrezParserBase):
    DATAFILE = 'gene/gene2unigene'
    def load(self, aslist=False):
        load_start(self.datafile)
        print
        geneid_d = get_geneid_d(self.species_li)
        gene2unigene = tab2dict(self.datafile, (0,1), 0, alwayslist=0,
                                includefn=lambda ld:int(ld[0]) in geneid_d)
        gene_d = {}
        for gid, unigene in gene2unigene.items():
            gene_d[gid] = {'unigene': unigene}
        load_done('[%d]' % len(gene_d))

        if aslist:
            return dict_to_list(gene_d)
        else:
            return gene_d

class Gene2GOParser(EntrezParserBase):
    DATAFILE = 'gene/gene2go.gz'

    def load(self, aslist=False):
        load_start(self.datafile)
        gene2go = tab2dict(self.datafile, (1,2,5,7), 0, alwayslist=1,
                           includefn=lambda ld:int(ld[0]) in self.taxid_set)
        category_d = {'Function': 'MF',
                      'Process':  'BP',
                      'Component': 'CC'}

        def _ff(d):
            out = {}
            for goid, goterm, gocategory in d:
                _gocategory = category_d[gocategory]
                _d = out.get(_gocategory, [])
                _d.append(dict(id=goid, term=goterm))
                out[_gocategory] = _d
            for k in out:
                if len(out[k]) == 1:
                    out[k] = out[k][0]
            return out

        gene2go = dict_convert(gene2go, valuefn=_ff)
        gene_d = {}
        for gid, go in gene2go.items():
            gene_d[gid] = {'go': go}
        load_done('[%d]' % len(gene_d))

        if aslist:
            return dict_to_list(gene_d)
        else:
            return gene_d


class Gene2RetiredParser(EntrezParserBase):
    '''
    loading ncbi gene_history file, adding "retired" field in gene doc
    '''

    DATAFILE = 'gene/gene_history.gz'
    def load(self, aslist=False):
        load_start(self.datafile)
        gene2retired = tab2dict(self.datafile, (1,2), 0, alwayslist=1,
                                includefn=lambda ld:int(ld[0]) in self.taxid_set and ld[1]!='-')
        gene2retired = dict_convert(gene2retired, valuefn=lambda x: normalized_value([int(xx) for xx in x]))

        gene_d = {}
        for gid, retired in gene2retired.items():
            gene_d[gid] = {'retired': retired}
        load_done('[%d]' % len(gene_d))

        if aslist:
            return dict_to_list(gene_d)
        else:
            return gene_d


class Gene2ECParser(EntrezParserBase):
    '''
    loading gene2ec data, adding "ec" field in gene doc

    Sample lines for input file:
        24159   2.3.3.8
        24161   3.1.3.2,3.1.3.48
    '''
    DATAFILE = 'refseq/gene2ec_all.txt'

    def load(self, aslist=False):
        load_start(self.datafile)
        with file(self.datafile) as df:
            geneid_set = set()
            doc_li = []
            for line in df:
                geneid, ec = line.strip().split('\t')
                if ec.find(',') != -1:
                    #there are multiple EC numbers
                    ec = ec.split(',')
                if geneid not in geneid_set:
                    doc_li.append(dict(_id=geneid, ec=unicode(ec)))
                    geneid_set.add(geneid)
        load_done('[%d]' % len(doc_li))

        if aslist:
            return doc_li
        else:
            gene_d = dict([(d['_id'], d) for d in doc_li])
            return gene_d
