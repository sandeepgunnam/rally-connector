#!env/bin/python2.7
import time, sys, os, logging, logging.config
from pyral import Rally, rallyWorkset
from flask import Flask, abort, request, json
from waitress import serve

# Logging setup
def setup_logging(
    default_path='logging.json',
    default_level=logging.INFO,
    env_key='LOG_CFG'
):
    # Setup logging configuration
    path = default_path
    value = os.getenv(env_key, None)
    if value:
        path = value
    if os.path.exists(path):
        with open(path, 'rt') as f:
            config = json.load(f)
        logging.config.dictConfig(config)
    else:
        logging.basicConfig(level=default_level)

setup_logging()
logger = logging.getLogger(__name__)

logger.info('Python: '+sys.version)

# Rally constants
apikey = '_UnNhJF1WT4ewX1tmWjBczIu2Jxa40sKiYn2D7n5AM'
user = 'bbowers@redhat.com'
password = '*redhat123'
server = 'rally1.rallydev.com'

# Setup API routes
app = Flask(__name__)

# GET PROJECTS
@app.route('/rally/api/v1/getProjects', methods=['POST'])
def post_subscribe():
    j = request.get_json()
    if not j or not 'project' in j or not 'workspace' in j:
        abort(400)

    workspace = j['workspace']
    project = j['project']

    # Setup working Rally object (to do stuff)
    rally = Rally(server, user, password, apikey=apikey, workspace='Red Hat IT Workspace', project='Team: IT Service Management')
    rally.enableLogging('mypyral.log')

    projects = rally.getProjects()
    resp = []

    for p in projects:
        resp.append({
            'name': str(p.Name),
            'id': str(p.oid),
            'uuid': str(p.ObjectUUID),
            'parent': '',
            'owner': ''
        })

        if hasattr(p.Parent, 'oid'):
            resp[ len(resp)-1 ]['parent'] = str(p.Parent.oid)

        if hasattr(p.Owner, 'UserName'):
            resp[ len(resp)-1 ]['owner'] = str(p.Owner.UserName)

    return json.dumps(resp);


# GET ITERATIONS
@app.route('/rally/api/v1/getIterations', methods=['POST'])
def post_iterations():
    j = request.get_json()
    if not j or not 'project' in j or not 'workspace' in j:
        abort(400)

    workspace = j['workspace']
    project = j['project']

    # Setup working Rally object (to do stuff)
    rally = Rally(server, user, password, apikey=apikey, workspace='Red Hat IT Workspace', project='Team: Run')
    rally.enableLogging('mypyral.log')

    iters = rally.get('Iteration')
    resp = []

    for p in iters:
        resp.append({
            'name': str(p.Name), 
            'uuid': str(p.ObjectUUID),
            'project': str(p.Project.ObjectUUID),
            'start': str(p.StartDate),
            'end': str(p.EndDate),
            'url': str(p._ref)
        })

    return json.dumps(resp)


# GET USERS
# Need Rally oid of users so that we can associate events
# All active users by default unless an email address is provided as query
@app.route('/rally/api/v1/getUsers', methods=['POST'])
def get_users():
    j = request.get_json()
    if not j or not 'project' in j or not 'workspace' in j:
        abort(400)

    workspace = j['workspace']
    project = j['project']

    # Setup working Rally object (to do stuff)
    rally = Rally(server, user, password, apikey=apikey, workspace='Red Hat IT Workspace', project='Team: Run')
    rally.enableLogging('mypyral.log')

    # Sanity check at least email address specified or allActiveUsers flag used
    if not 'singleUserEmailAddress' in j and not 'allActiveUsers' in j:
        abort(400)
    
    if 'singleUserEmailAddress' in j:
        rusers = rally.get('User', query='UserName = "'+j['singleUserEmailAddress']+'"')
        
        if rusers.resultCount != 1:
            abort(400)

        ruser = rusers.next()
        resp = {
            "oid": str(ruser.ObjectID),
            "uuid": str(ruser.ObjectUUID),
            "email": str(ruser.UserName)
        }

    # Get all users
    elif 'allActiveUsers' in j:
        resp = []
        
        rusers = rally.get('User', query='Role = ""')
        for ruser in rusers:
            resp.append({
                "oid": str(ruser.ObjectID),
                "uuid": str(ruser.ObjectUUID),
                "email": str(ruser.UserName)
            })
        
        rusers = rally.get('User', query='Role != ""')
        for ruser in rusers:
            resp.append({
                "oid": str(ruser.ObjectID),
                "uuid": str(ruser.ObjectUUID),
                "email": str(ruser.UserName)
            })

    return json.dumps(resp)


# Create/Update Rally Object
# POST
@app.route('/rally/api/v1/updateObject', methods=['POST'])
def post_update_object():
    j = request.get_json()
    if not j or not 'project' in j or not 'workspace' in j:
        abort(400)

    workspace = j['workspace']
    project = j['project']

    # Setup working Rally object (to do stuff)
    rally = Rally(server, user, password, apikey=apikey, workspace='Red Hat IT Workspace', project=project)
    rally.enableLogging('mypyral.log')

    # Sanity check basic info to perform create/update are present
    if not 'entityName' in j or not 'entityBody' in j:
        abort(400)

    # Add Owner reference if exists
    if 'Owner' in j['entityBody']:
        users = rally.get('User', query='UserName = "'+j['entityBody']['Owner']+'"')
        
        if users.resultCount == 1:
            j['entityBody']['Owner'] = users.next().ref
        else: del j['entityBody']['Owner']

    # Add CreatedBy reference if exists
    if 'CreatedBy' in j['entityBody']:
        users = rally.get('User', query='UserName = "'+j['entityBody']['CreatedBy']+'"')

        if users.resultCount == 1:
            j['entityBody']['CreatedBy'] = users.next().ref
        else: del j['entityBody']['CreatedBy']

    # Sanity check that create/update action defined
    if 'action' not in j:
        return false

    # Create Rally object
    if j['action'] == 'create':
        rObject = rally.put(j['entityName'], j['entityBody'])

    # Update Rally object
    else: rObject = rally.post(j['entityName'], j['entityBody'])

    # Add comment (if exists)
    if 'entityComment' in j and 'entityOID' in j:
        rally.create('ConversationPost', {"Artifact": j['entityOID'], "Text": j['entityComment']})

    # Add work notes (if exists)
    if 'entityWorkNotes' in j and 'entityOID' in j:
        rally.create('ConversationPost', {"Artifact": j['entityOID'], "Text": j['entityWorkNotes']})

    # Build response
    resp = {
        "FormattedID": str(rObject.FormattedID),
        "Name": str(rObject.Name),
        "oid": str(rObject.oid),
        "ScheduleState": str(rObject.ScheduleState)
    }

    # Add Owner to response (email address)
    if rObject.Owner == None:
        resp['Owner'] = ''
    else: resp['Owner'] = rObject.Owner.EmailAddress

    # Return stringified JSON response / status code: 200
    return json.dumps(resp)


if __name__ == '__main__':
    serve(app, host='127.0.0.1', port=5050)
