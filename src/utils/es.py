from pyes import ES
from pyes.exceptions import (NotFoundException, IndexMissingException,
                             ElasticSearchException, TypeMissingException)
from pyes.query import MatchAllQuery
from pyes.utils import make_path
import logging
log = logging.getLogger('pyes')
log.setLevel(logging.DEBUG)
if len(log.handlers) == 0:
    log_handler = logging.StreamHandler()
    log.addHandler(log_handler)

from config import ES_HOST, ES_INDEX_NAME, ES_INDEX_TYPE
from utils.common import ask
from utils.mongo import doc_feeder

import sys


def get_es():
    conn = ES(ES_HOST, default_indices=[ES_INDEX_NAME],
              timeout=120.0, max_retries=10)
    return conn


def lastexception():
    exc_type,exc_value,tb = sys.exc_info()
    if exc_type is None:
        print "No exception occurs."
        return
    print exc_type.__name__ + ':' ,
    try:
        excArgs = exc_value.__dict__["args"]
    except KeyError:
        excArgs = ()
    return str(exc_type)+':'+''.join([str(x) for x in excArgs])

class ESIndexer(object):
    def __init__(self, es_index_name=None, es_index_type=None, mapping=None):
        self.conn = get_es()
        self.ES_INDEX_NAME = es_index_name or ES_INDEX_NAME
        self.ES_INDEX_TYPE = es_index_type or ES_INDEX_TYPE
        self.step = 10000
        self.s = None     #optionally, can specify number of records to skip,
                          #useful to continue indexing after an error.
        self.use_parallel = False
        self._mapping = mapping

    def check(self):
        '''print out ES server info for verification.'''
        print "Servers:", self.conn.servers
        print "Default indices:", self.conn.default_indices
        print "ES_INDEX_TYPE:", self.ES_INDEX_TYPE

    def create_index(self):
        try:
            print self.conn.open_index(self.ES_INDEX_NAME)
        except IndexMissingException:
            print self.conn.create_index(self.ES_INDEX_NAME)

    def delete_index_type(self, index_type, noconfirm=False):
        '''Delete all indexes for a given index_type.'''
        index_name = self.ES_INDEX_NAME
        #Check if index_type exists
        try:
            self.conn.get_mapping(index_type, index_name)
        except TypeMissingException:
            print 'Error: index type "%s" does not exist in index "%s".' % (index_type, index_name)
            return
        path = '/%s/%s' % (index_name, index_type)
        if noconfirm or ask('Confirm to delete all data under "%s":' % path) == 'Y':
            return self.conn.delete_mapping(index_name, index_type)

    def verify_mapping(self, update_mapping=False):
        '''Verify if index and mapping exist, update mapping if mapping does not exist,
           or "update_mapping=True" explicitly
        '''
        conn = self.conn
        index_name = self.ES_INDEX_NAME
        index_type = self.ES_INDEX_TYPE

        #Test if index exists
        try:
            print "Opening index...", conn.open_index(index_name)
        except NotFoundException:
            print 'Error: index "%s" does not exist. Create it first.' % index_name
            return -1

        try:
            conn.get_mapping(index_type, index_name)
            empty_mapping = False
        except ElasticSearchException:
            #if no existing mapping available for index_type
            #force update_mapping to True
            empty_mapping = True
            update_mapping = True

#        empty_mapping = not cur_mapping[index_name].get(index_type, {})
#        if empty_mapping:
#            #if no existing mapping available for index_type
#            #force update_mapping to True
#            update_mapping = True

        if update_mapping:
            print "Updating mapping...",
            if not empty_mapping:
                print "\n\tRemoving existing mapping...",
                print conn.delete_mapping(index_name, index_type)
            _mapping = self.get_field_mapping()
            print conn.put_mapping(index_type,
                                   _mapping,
                                   [index_name])
    def count(self, query=None, index_type=None):
        conn = self.conn
        index_name = self.ES_INDEX_NAME
        index_type = index_type or self.ES_INDEX_TYPE
        return conn.count(query, index_name, index_type)

    def get(self, id, **kwargs):
        '''get a specific doc by its id.'''
        conn = self.conn
        index_name = self.ES_INDEX_NAME
        index_type = self.ES_INDEX_TYPE
        return conn.get(index_name, index_type, id, **kwargs)

    def index(self, doc, id=None):
        '''add a doc to the index. If id is not None, the existing doc will be
           updated.
        '''
        return self.conn.index(doc, self.ES_INDEX_NAME, self.ES_INDEX_TYPE, id=id)

    def delete_doc(self, index_type, id):
        '''delete a doc from the index based on passed id.'''
        return self.conn.delete(self.ES_INDEX_NAME, index_type, id)

    def update(self, id, extra_doc, index_type=None):
        '''update an existing doc with extra_doc.'''
        conn = self.conn
        index_name = self.ES_INDEX_NAME
        index_type = index_type or self.ES_INDEX_TYPE
        # old way, update locally and then push it back.
        # return self.conn.update(extra_doc, self.ES_INDEX_NAME,
        #                         index_type, id)

        #using new update api since 0.20
        path = make_path((index_name, index_type, id, '_update'))
        body = {'doc': extra_doc}
        return conn._send_request('POST', path, body=body)


    def optimize(self):
        '''optimize the default index.'''
        return self.conn.indices.optimize(self.ES_INDEX_NAME,
                                          wait_for_merge=True,
                                          max_num_segments=5)

    def optimize_all(self):
        """optimize all indices"""
        return self.conn.indices.optimize([], wait_for_merge=True,
                                              max_num_segments=5)

    def get_field_mapping(self):
#        raise NotImplementedError
        return self._mapping

    def build_index(self, collection, update_mapping=False, verbose=False):
        conn = self.conn
        index_name = self.ES_INDEX_NAME
        #index_type = self.ES_INDEX_TYPE

        self.verify_mapping(update_mapping=update_mapping)
        #update some settings for bulk indexing
        conn.indices.update_settings(index_name,
            {
                "refresh_interval" : "-1",              #disable refresh temporarily
                "index.store.compress.stored": True,    #store-level compression
                #"index.store.compress.tv": True,        #store-level compression
            })
        try:
            print "Building index..."
            if self.use_parallel:
                cnt = self._build_index_parallel(collection, verbose)
            else:
                cnt = self._build_index_sequential(collection, verbose)
        finally:
            #restore some settings after bulk indexing is done.
            conn.indices.update_settings(index_name,
                {
                    "refresh_interval" : "1s",              #default settings
                })
            print conn.flush()
            print conn.refresh()

        print 'Done! - {} docs indexed.'.format(cnt)

    def _build_index_sequential(self, collection, verbose=False):
        conn = self.conn
        index_name = self.ES_INDEX_NAME
        index_type = self.ES_INDEX_TYPE
        cnt = 0
        for doc in doc_feeder(collection, step=self.step, s=self.s):
            conn.index(doc, index_name, index_type, doc['_id'], bulk=True)
            cnt += 1
            if verbose:
                print cnt, ':', doc['_id']
        return cnt

    def _build_index_parallel(self, collection, verbose=False):
        from utils.parallel import (run_jobs_on_ipythoncluster,
                                    collection_partition,
                                    require)
        kwargs_common = {'ES_HOST': ES_HOST,
                         'ES_INDEX_NAME': self.ES_INDEX_NAME,
                         'ES_INDEX_TYPE': self.ES_INDEX_TYPE,
                         }
        task_list = []
        for kwargs in collection_partition(collection, step=self.step):
            kwargs.update(kwargs_common)
            task_list.append(kwargs)


        @require('mongokit', 'pyes')
        def worker(kwargs):
            server = kwargs['server']
            port = kwargs['port']
            src_db = kwargs['src_db']
            src_collection = kwargs['src_collection']
            skip = kwargs['skip']
            limit = kwargs['limit']

            mongo_conn = mongokit.Connection(server, port)
            src = mongo_conn[src_db]


            ES_HOST = kwargs['ES_HOST']
            ES_INDEX_NAME = kwargs['ES_INDEX_NAME']
            ES_INDEX_TYPE = kwargs['ES_INDEX_TYPE'],

            es_conn = pyes.ES(ES_HOST, default_indices=[ES_INDEX_NAME],
                              timeout=120.0, max_retries=10)

            cur = src[src_collection].find(skip=skip, limit=limit, timeout=False)
            cur.batch_size(1000)
            cnt = 0
            try:
                for doc in cur:
                    es_conn.index(doc, ES_INDEX_NAME, ES_INDEX_TYPE, doc['_id'], bulk=True)
                    cnt += 1
            finally:
                cur.close()
            es_conn.flush()   #this is important to avoid missing docs
            return cnt

        job_results = run_jobs_on_ipythoncluster(worker, task_list)
        cnt = sum(job_results)
        return cnt

    def get_id_list(self, index_type=None, index_name=None, step=10000):
        '''return a list of all doc ids in an index_type.'''
        conn = self.conn
        index_name = index_name or self.ES_INDEX_NAME
        index_type = index_type or self.ES_INDEX_TYPE

        id_li = []
        q = MatchAllQuery()
        res = conn.search_raw(q, indices=index_name, doc_types=index_type,
                              size=step, scan=True, scroll='5m', fields=[])
        id_li.extend([doc['_id'] for doc in res.hits.hits])
        while 1:
            res = conn.search_scroll(res._scroll_id, scroll='5m')
            if len(res.hits.hits) == 0:
                break
            else:
                id_li.extend([doc['_id'] for doc in res.hits.hits])
        return id_li
