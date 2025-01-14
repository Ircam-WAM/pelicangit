import socketserver
import http.server
import os
import re
from pelican import main
from pelicangit.gitbindings import *

GET_RESPONSE_BODY = "<h1>PelicanGit is Running</h1>"
POST_RESPONSE_BODY = "<h1>Pelican Project Rebuilt</h1>"
ERROR_RESPONSE_BODY = "<h1>Error</h1>"


class GitHookServer(socketserver.TCPServer):

    def __init__(self, server_address, handler_class, source_repo, deploy_repo, whitelisted_files):
        self.source_repo = source_repo
        self.deploy_repo = deploy_repo
        self.whitelisted_files = whitelisted_files
        socketserver.TCPServer.__init__(self, server_address, handler_class)
        return


class GitHookRequestHandler(http.server.SimpleHTTPRequestHandler):

    def do_GET(self):
        self.do_response(GET_RESPONSE_BODY.encode())

    def do_POST(self):
        try:
            if isinstance(self.server.source_repo.branches, list):
                for branch in self.server.source_repo.branches:
                    print(branch)
                    self.do_produce_branch(branch)
            else:
                self.do_produce_branch(self.server.source_repo.branch)

            self.do_response(POST_RESPONSE_BODY.encode())

        except Exception as e:
            print(e)

            #In the event of an excepion, hard reset both repos so they match the remote (origin) master branches
            self.hard_reset_source_repos('master')
            if not self.server.deploy_repo.is_local_dir:
                self.hard_reset_deploy_repos('master')

            self.do_response(ERROR_RESPONSE_BODY.encode())

    def do_produce_branch(self, branch):
        #Hard reset both repos so they match the remote (origin) branches
        self.hard_reset_source_repos(branch)

        if not self.server.deploy_repo.is_local_dir:
            self.hard_reset_deploy_repos(branch)

            # Git Remove all deploy_repo files (except those whitelisted) and then rebuild with pelican
            self.nuke_git_cwd(self.server.deploy_repo)
            main()

            # Add all files newly created by pelican, then commit and push everything
            self.server.deploy_repo.add(['.'])

            commit_message = self.server.source_repo.log(['-n1', '--pretty=format:"%h %B"'])
            self.server.deploy_repo.commit(commit_message, ['-a'])
            self.server.deploy_repo.push([self.server.deploy_repo.origin, self.server.deploy_repo.master])
        else:
            try:
                main()
            except:
                pass

    def do_response(self, resBody):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.send_header("Content-length", len(resBody))
        self.end_headers()
        self.wfile.write(resBody)

    def hard_reset_source_repos(self, branch):
        self.server.source_repo.fetch([self.server.source_repo.origin])
        self.server.source_repo.checkout([branch])
        self.server.source_repo.reset(['--hard', 'origin/' + branch])

    def hard_reset_deploy_repos(self, branch=None):
        self.server.deploy_repo.fetch([self.server.deploy_repo.origin])
        self.server.deploy_repo.checkout([branch])
        self.server.deploy_repo.reset(['--hard', 'origin/' + branch])

    def nuke_git_cwd(self, git_repo):
        for root, dirs, files in os.walk(git_repo.repoDir):
            #If we are anywhere in the .git directory, then skip this iteration
            if re.match("^.*\.git(/.*)?$", root): continue

            local_dir = root.replace(git_repo.repoDir + "/", "")
            local_dir = local_dir.replace(git_repo.repoDir, "")

            for f in files:
                local_file = os.path.join(local_dir, f)
                if local_file not in self.server.whitelisted_files:
                    git_repo.rm(['-r', local_file])
