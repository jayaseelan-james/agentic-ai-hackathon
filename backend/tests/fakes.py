class FakeProvider:
    model = 'test-model'

    def __init__(self, responses=None):
        self.inputs = []
        self.uploads = []
        self.deleted = []
        self.responses = responses
        self.fail = False

    async def create(self, **body):
        self.inputs.append(body)
        if self.fail:
            raise RuntimeError('sensitive provider exception')
        if self.responses is not None:
            return self.responses.pop(0)
        if len(self.inputs) == 1:
            return {'id':'interaction-1', 'status':'requires_action', 'steps':[{'type':'function_call','name':'get_vehicle_profile','arguments':{},'id':'call-1'}]}
        text = 'Check the vehicle label while safely parked. The cause is unconfirmed.'
        return {'id':'interaction-2','status':'completed','steps':[
            {'type':'google_search_call','arguments':{'queries':['manufacturer tire warning']}},
            {'type':'google_search_result','result':[{'search_suggestions':'<p>Google Search suggestions</p>'}]},
            {'type':'model_output','content':[{'type':'text','text':text,'annotations':[{'type':'url_citation','url':'https://example.com/manual','title':'Official source','start_index':0,'end_index':42}]}]},
        ]}

    async def upload(self, data, mime):
        self.uploads.append((data, mime))
        return {'name':f'files/{len(self.uploads)}','uri':'https://files.example/test','state':'ACTIVE'}

    async def file(self, name):
        return {'name':name,'uri':'https://files.example/test','state':'ACTIVE'}

    async def delete(self, name):
        self.deleted.append(name)

    async def close(self):
        pass
