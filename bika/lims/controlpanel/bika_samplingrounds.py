from plone.supermodel import model
from plone.dexterity.content import Container
from zope.interface import implements
from bika.lims.browser.bika_listing import BikaListingView
from plone.app.content.browser.interfaces import IFolderContentsView
from plone.app.layout.globals.interfaces import IViewView
from bika.lims import bikaMessageFactory as _


class SamplingRoundsView(BikaListingView):
    """Displays all system's sampling rounds
    """
    implements(IFolderContentsView, IViewView)

    def __init__(self, context, request):
        super(SamplingRoundsView, self).__init__(context, request)
        self.catalog = "portal_catalog"
        self.contentFilter = {
            'portal_type': 'SamplingRound',
            'sort_on': 'sortable_title'
        }
        self.show_table_only = False
        self.show_sort_column = False
        self.show_select_row = False
        self.show_select_column = True
        self.pagesize = 25
        self.form_id = "samplinground"
        self.icon = self.portal_url + "/++resource++bika.lims.images/instrumentcertification_big.png"
        self.title = self.context.translate(_("Sampling Rounds"))
        self.description = ""
        # Hide the ugly edit-bar with 'new', 'draft', etc
        # self.request.set('disable_border', 1)
        self.columns = {
            'title': {'title': _('Title'),
                      'sortable': True,
                      'toggle': True},
            'Description': {'title': _('Description')},
            'num_sample_points': {'title': _('Number of sampling points'),
                                    'index': 'sortable_title'},
            'num_containers': {'title': _('Number of containers'),
                               'index': 'sortable_title'},
        }
        self.review_states = [
            {'id': 'default',
             'title': _('All'),
             'contentFilter':{},
             'columns': ['title',
                         'Description',
                         ],
             'transitions': [],
             },
        ]

    def folderitems(self, full_objects=True):
        items = BikaListingView.folderitems(self, full_objects)
        for x in range(len(items)):
            if not items[x].has_key('obj'): continue
            obj = items[x]['obj']
            items[x]['title'] = obj.Title()
            items[x]['replace']['title'] = "<a href='%s'>%s</a>" % \
                 (items[x]['url'], items[x]['title'])
            #items[x]['num_sample_points'] = obj.num_sample_points
            #items[x]['num_containers'] = obj.num_containers
        return items


class ISamplingRounds(model.Schema):
    """A conference program. Programs can contain Sessions.
    """

# Custom content-type class; objects created for this content type will
# be instances of this class. Use this class to add content-type specific
# methods and properties. Put methods that are mainly useful for rendering
# in separate view classes.


class SamplingRounds(Container):
    implements(ISamplingRounds)
    # Add your class methods and properties here
    displayContentsTab = False
    pass
