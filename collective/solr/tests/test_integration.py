from unittest import TestSuite, makeSuite, main
from zope.testing.doctest import ELLIPSIS, NORMALIZE_WHITESPACE
from Testing.ZopeTestCase import FunctionalDocFileSuite
from collective.solr.tests.base import SolrTestCase, SolrFunctionalTestCase
from plone.app.controlpanel.tests.cptc import ControlPanelTestCase


# test-specific imports go here...
from zope.component import queryUtility, getUtilitiesFor
from collective.indexing.interfaces import IIndexQueueProcessor
from collective.solr.interfaces import ISolrConnectionManager
from collective.solr.interfaces import ISolrIndexQueueProcessor
from collective.solr.interfaces import ISearch
from collective.solr.exceptions import SolrInactiveException
from collective.solr.tests.utils import getData, fakehttp
from transaction import commit


class UtilityTests(SolrTestCase):

    def testGenericInterface(self):
        proc = queryUtility(IIndexQueueProcessor, name='solr')
        self.failUnless(proc, 'utility not found')
        self.failUnless(IIndexQueueProcessor.providedBy(proc))
        self.failUnless(ISolrIndexQueueProcessor.providedBy(proc))

    def testSolrInterface(self):
        proc = queryUtility(ISolrIndexQueueProcessor, name='solr')
        self.failUnless(proc, 'utility not found')
        self.failUnless(IIndexQueueProcessor.providedBy(proc))
        self.failUnless(ISolrIndexQueueProcessor.providedBy(proc))

    def testRegisteredProcessors(self):
        procs = list(getUtilitiesFor(IIndexQueueProcessor))
        self.failUnless(procs, 'no utilities found')
        solr = queryUtility(ISolrIndexQueueProcessor, name='solr')
        self.failUnless(solr in [util for name, util in procs], 'solr utility not found')

    def testSearchInterface(self):
        search = queryUtility(ISearch)
        self.failUnless(search, 'search utility not found')
        self.failUnless(ISearch.providedBy(search))


class IndexingTests(SolrTestCase):

    def afterSetUp(self):
        schema = getData('plone_schema.xml')
        self.proc = queryUtility(ISolrConnectionManager)
        self.proc.setHost(active=True)
        conn = self.proc.getConnection()
        fakehttp(conn, schema)          # fake schema response
        self.proc.getSchema()           # read and cache the schema

    def beforeTearDown(self):
        self.proc.closeConnection(clearSchema=True)
        # due to the `commit()` in the tests below from `afterSetUp` need
        # to be explicitly reversed (and committed)...
        self.proc.setHost(active=False)
        commit()

    def testIndexObject(self):
        output = []
        connection = self.proc.getConnection()
        responses = getData('add_response.txt'), getData('commit_response.txt')
        output = fakehttp(connection, *responses)           # fake responses
        self.folder.processForm(values={'title': 'Foo'})    # updating sends data
        self.assertEqual(self.folder.Title(), 'Foo')
        self.assertEqual(str(output), '', 'reindexed unqueued!')
        commit()                        # indexing happens on commit
        required = '<field name="Title">Foo</field>'
        self.assert_(str(output).find(required) > 0, '"title" data not found')

    def testNoIndexingWithoutUniqueKey(self):
        self.setRoles(('Manager',))
        output = []
        connection = self.proc.getConnection()
        responses = [getData('dummy_response.txt')] * 42    # set up enough...
        output = fakehttp(connection, *responses)           # fake responses
        self.folder.invokeFactory('Topic', id='coll', title='a collection')
        self.folder.coll.addCriterion('Type', 'ATPortalTypeCriterion')
        self.assertEqual(str(output), '', 'reindexed unqueued!')
        commit()                        # indexing happens on commit
        self.assert_(repr(output).find('a collection') > 0, '"title" data not found')
        self.assert_(repr(output).find('crit') == -1, 'criterion indexed?')
        objs = self.portal.portal_catalog(portal_type='ATPortalTypeCriterion')
        self.assertEqual(list(objs), [])


class SiteSearchTests(SolrTestCase):

    def beforeTearDown(self):
        # resetting the solr configuration after each test isn't strictly
        # needed at the moment, but it triggers the `ConnectionStateError`
        # when the other tests (in `errors.txt`) is trying to perform an
        # actual solr search...
        queryUtility(ISolrConnectionManager).setHost(active=False)

    def testSkinSetup(self):
        skins = self.portal.portal_skins.objectIds()
        self.failUnless('solr_site_search' in skins, 'no solr skin?')

    def testInactiveException(self):
        search = queryUtility(ISearch)
        self.assertRaises(SolrInactiveException, search, 'foo')


def test_suite():
    return TestSuite([
        makeSuite(UtilityTests),
        makeSuite(IndexingTests),
        makeSuite(SiteSearchTests),
        FunctionalDocFileSuite('configlet.txt',
            optionflags=ELLIPSIS | NORMALIZE_WHITESPACE,
            package='collective.solr.tests',
            test_class=ControlPanelTestCase),
        FunctionalDocFileSuite('errors.txt',
            optionflags=ELLIPSIS | NORMALIZE_WHITESPACE,
            package='collective.solr.tests',
            test_class=SolrFunctionalTestCase),
    ])

if __name__ == '__main__':
    main(defaultTest='test_suite')

