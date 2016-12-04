import neovim, os, json, subprocess, socket, platform, subprocess,re, string, time

@neovim.plugin
class Tern(object):
    def __init__(self, nvim):
        self.nvim = nvim
        self.port = None
        self.proc = None

    @neovim.autocmd('VimLeave', pattern="*", sync=False)
    def on_vimleave(self):
        if self.proc is None: return
        self.proc.stdin.close()
        self.proc.wait()
        self.proc = None

    @neovim.autocmd('VimEnter', pattern="*", sync=False)
    def on_vimenter(self):
        self.nvim.command('let g:x=1')
        command = self.nvim.eval("g:tern#command") + self.nvim.eval("g:tern#arguments")
        project_dir = self.project_dir()
        if project_dir == '':
            return
        portFile = os.path.join(project_dir, ".tern-port")
        if os.path.isfile(portFile):
            port = int(open(portFile, "r").read())
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('127.0.0.1', int(port)))
            if result == 0:
                sock.close()
                return
        self.start_server(command, project_dir)

    def project_dir(self):
        project_dir = ""
        mydir = self.nvim.eval("expand('%:p:h')")
        if not os.path.isdir(mydir): return ""

        if mydir:
            while True:
                parent = os.path.dirname(mydir[:-1])
                if not parent:
                    return ""
                if os.path.isfile(os.path.join(mydir, ".tern-project")):
                    project_dir = mydir
                    break
                mydir = parent
        self.nvim.command("let b:ternProjectDir = " + json.dumps(project_dir))
        return project_dir

    def start_server(self, command, project_dir):
        win = platform.system() == "Windows"
        env = None
        if platform.system() == "Darwin":
            env = os.environ.copy()
        try:
            proc = subprocess.Popen(command,
                                    cwd=project_dir, env=env,
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, shell=win)
        except Exception as e:
            self.display_error("Failed to start server: " + str(e))
            return None
        output = ""
        while True:
            line = proc.stdout.readline().decode('utf8')
            if not line:
                tern_displayError("Failed to start server" + (output and ":\n" + output))
                project.last_failed = time.time()
                return None
            match = re.match("Listening on port (\\d+)", line)
            if match:
                port = int(match.group(1))
                self.port = port
                self.proc = proc
                return port
            else:
                output += line

    def display_error(self, err):
        self.nvim.command("echohl Error")
        self.nvim.command("echo '" + str(err).replace("'", "''") + "'")
        self.nvim.command("echohl None")
