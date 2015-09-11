#!/usr/bin/env python
import sys
import os
import json
import codecs

import cpapi
import cputils

class CmdLine:
    def __init__(self):
        self.authFilename = "issues.auth"
        self.groupName = None # translates to root
        self.recurse = True
        self.format = None
        self.outfile = None
        self.startingDate = None
        self.progdir = None
        self.verbose = False
        self.apistats = False
        self.pageSize = 100
        self.activeOnly = True # may eventually be able to override this, if desired
        self.detailed = False
        self.scantypes = None
        self.base = "https://portal-perf.cloudpassage.com"

    def processArgs(self, argv):
        allOK = True
        outfilename = None
        self.progdir = os.path.dirname(sys.argv[0])
        for arg in argv[1:]:
            if (arg == "--apistats") or (arg == "--apistat"):
                self.apistats = True
            elif (arg.startswith("--auth=")):
                self.authFilename = arg.split("=")[1]
            elif (arg.startswith("--group=")):
                self.groupName = arg.split("=")[1]
            elif (arg.startswith("--base=")):
                self.base = arg.split("=")[1]
            elif (arg == "-h") or (arg == "-?"):
                allOK = False
            elif (arg == "-v") or (arg == "--verbose"):
                self.verbose = True
            elif (arg == "--detailed"):
                self.detailed = True
            elif (arg.startswith("--scan=")):
                self.scantypes = arg.split("=")[1]
                typelist = self.scantypes.split(",")
                for type in typelist:
                    if not(type in [ "fim", "csm", "svm" ]):
                        print >>sys.stderr, "Unknown scan type: %s" % type
                        allOK = False
            else:
                print >>sys.stderr, "Unknown argument: %s" % arg
                allOK = False
        return allOK

    def usage(self, progname):
        print >> sys.stderr, "Usage: %s [flag] [...]" % os.path.basename(progname)
        print >> sys.stderr, "Where flag is one or more of the following options:"
        print >> sys.stderr, "--auth=<filename>\tSpecify name of file containing API credentials"
        print >> sys.stderr, "--detailed\t\tDisplays details of each issue reported by Halo"
        print >> sys.stderr, "--scan=<type_or_types>\tLimit results to one or more scan types (comma separated)"
        print >> sys.stderr, "--base=<url>\t\tSpecify the URL of the Halo REST API"
        print >> sys.stderr, "--apistats\t\tDisplays performance stats of REST API usage"

class IssuesReport:
    def __init__(self):
        self.api = cpapi.CPAPI()

    def listGroups(self):
        url = "%s:%d/v2/groups" % (self.api.base_url, self.api.port)
        (data, authError) = self.api.doGetRequest(url, self.api.authToken)
        if (data):
            return (json.loads(data), authError)
        else:
            return (None, authError)

    def listServersInGroup(self, groupID, activeOnly = True, pageSize = 100):
        url = "%s:%d/v2/servers?group_id=%s&per_page=%d" % (self.api.base_url, self.api.port, groupID, pageSize)
        if (activeOnly):
            url += "&status=active"
        return url

    def listMoreServersInGroup(self, url):
        (data, authError) = self.api.doGetRequest(url, self.api.authToken)
        if (data):
            return (json.loads(data), authError)
        else:
            return (None, authError)

    def listIssuesByServer(self, serverID, scanTypes):
        url = "%s:%d/v2/issues?agent_id=%s&state=active" % (self.api.base_url, self.api.port, serverID)
        if (scanTypes != None):
            url += "&issue_type=%s" % scanTypes
        (data, authError) = self.api.doGetRequest(url, self.api.authToken)
        if (data):
            return (json.loads(data), authError)
        else:
            return (None, authError)

    def getIssueDetails(self, issueID):
        url = "%s:%d/v2/issues/%s" % (self.api.base_url, self.api.port, issueID)
        (data, authError) = self.api.doGetRequest(url, self.api.authToken)
        if (data):
            return (json.loads(data), authError)
        else:
            return (None, authError)

    def dumpGroup(self, group, prefix, grplist, cmd):
        print "%s%s [%s]" % (prefix, group['name'], group['tag'])
        print "%s  id=%s" % (prefix, group['id'])
        if (cmd.recurse) and ('has_children' in group) and (group['has_children']):
            for child in grplist:
                if ('parent_id' in child) and (group['id'] == child['parent_id']):
                    self.dumpGroup(child,prefix + '  ',grplist, cmd)

    def getTypeCount(self, countMap, typeName):
        if (typeName in countMap):
            return countMap[typeName]
        else:
            return 0

    def printApiStats(self, cmd):
        if (cmd.apistats):
            (apicount, apitime) = self.api.getTimeLog()
            if (apicount != 0):
                print >> sys.stderr, "ApiStats: count=%d time=%g avgTime=%g" % ( apicount, apitime, apitime / apicount )
            else:
                print >> sys.stderr, "ApiStats: count=0 time=0.0 avgTime=0.0"

    def processServer(self, group, server, cmd):
        ( report, authError ) = self.listIssuesByServer(server['id'],cmd.scantypes)
        typeCounts = {}
        totalIssueCount = 0
        if (report == None) or (authError):
            self.api.authenticateClient()
            ( report, authError ) = self.listIssuesByServer(server['id'],cmd.scantypes)
        if (report == None):
            return
        if (cmd.detailed):
            if ('issues' in report):
                issueList = report['issues']
                for issue in issueList:
                    if ('id' in issue):
                        (details, authError) = self.getIssueDetails(issue['id'])
                        if (details == None) or (authError):
                            self.api.authenticateClient()
                            (details, authError) = self.getIssueDetails(issue['id'])
                        if (details != None):
                            print "%s" % json.dumps(details,indent=4)                            
        else:
            print "%s" % json.dumps(report,indent=4)

    def processGroup(self, group, grplist, cmd):
        nextLink = self.listServersInGroup(group['id'],cmd.activeOnly,cmd.pageSize)
        while (nextLink != None):
            ( serverListObj, authError ) = self.listMoreServersInGroup(nextLink)
            self.printApiStats(cmd)
            nextLink = None
            if (serverListObj != None):
                if ('servers' in serverListObj):
                    for server in serverListObj['servers']:
                        self.processServer(group,server,cmd)
                if ('pagination' in serverListObj):
                    paginationObj = serverListObj['pagination']
                    if ('next' in paginationObj):
                        nextLink = paginationObj['next']
        if (cmd.recurse) and ('has_children' in group) and (group['has_children']):
            for child in grplist:
                if ('parent_id' in child) and (group['id'] == child['parent_id']):
                    self.processGroup(child,grplist, cmd)

    def run(self,cmd):
        (credentialList, errMsg) = cputils.processAuthFile(cmd.authFilename, cmd.progdir)
        if (errMsg != None):
            print >> sys.stderr, errMsg
            return False
        if len(credentialList) < 1:
            return False
        # print credentials
        credentials = credentialList[0]
        self.api.base_url = cmd.base
        self.api.key_id = credentials['id']
        self.api.secret = credentials['secret']
        resp = self.api.authenticateClient()
        if (not resp):
            return False
        ( groupListObj, authError ) = self.listGroups()
        groupListCount = groupListObj['count']
        if (cmd.verbose):
            print >>  sys.stderr, "Found %d groups in list" % groupListCount
        if 'groups' in groupListObj:
            grplist = groupListObj['groups']
            for group in grplist:
                if ((cmd.groupName == None) and (group['parent_id'] == None)):
                    # self.dumpGroup(group,'',grplist,cmd.recurse)
                    self.processGroup(group,grplist,cmd)
                elif (cmd.groupName == group['name']):
                    # self.dumpGroup(group,'',grplist,cmd.recurse)
                    self.processGroup(group,grplist,cmd)
        return True

if __name__ == "__main__":
    cmd = CmdLine()
    if not cmd.processArgs(sys.argv):
        cmd.usage(sys.argv[0])
    else:
        rep = IssuesReport()
        rep.run(cmd)
