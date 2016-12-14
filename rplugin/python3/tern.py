import neovim, os, json, socket, platform, re, string, time, webbrowser
import sys
from urllib import request
from urllib.error import HTTPError

def cmp(a, b):
  if a < b:
    return -1
  elif a > b:
    return 1
  else:
    return 0

# Copied here because Python 2.6 and lower don't have it built in, and
# python 3.0 and higher don't support old-style cmp= args to the sort
# method. There's probably a better way to do this...
def tern_cmp_to_key(mycmp):
  class K(object):
    def __init__(self, obj, *args):
      self.obj = obj
    def __lt__(self, other):
      return mycmp(self.obj, other.obj) < 0
    def __gt__(self, other):
      return mycmp(self.obj, other.obj) > 0
    def __eq__(self, other):
      return mycmp(self.obj, other.obj) == 0
    def __le__(self, other):
      return mycmp(self.obj, other.obj) <= 0
    def __ge__(self, other):
      return mycmp(self.obj, other.obj) >= 0
    def __ne__(self, other):
      return mycmp(self.obj, other.obj) != 0
  return K

from itertools import groupby
opener = request.build_opener(request.ProxyHandler({}))

@neovim.plugin
class Tern(object):
  def __init__(self, nvim):
    self.nvim = nvim
    self.port = None
    self.root = ''

  @neovim.function("TernConfig", sync=False)
  def config(self, args):
    self.root = args[0]
    self.port = args[1]

  def display_error(self, err):
    self.nvim.command("echohl Error")
    self.nvim.command("echo '" + str(err).replace("'", "''") + "'")
    self.nvim.command("echohl None")

  def makeRequest(self, doc, silent=False):
    if self.port is None: return
    payload = json.dumps(doc)
    payload = payload.encode('utf-8')
    port = self.port
    timeout = float(self.nvim.eval("g:tern_request_timeout"))
    try:
      req = opener.open("http://localhost:" + str(port) + "/", payload, timeout)
      result = req.read()
      result = result.decode('utf-8')
      return json.loads(result)
    except HTTPError as error:
      if not silent:
        message = error.read()
        message = message.decode('utf-8')
        self.display_error(message)
    return None

  def relativeFile(self):
    filename = self.nvim.eval("expand('%:p')")
    return filename[len(self.root) + 1:]

  def bufferSlice(self, buf, pos, end):
    text = ""
    while pos < end:
      text += buf[pos] + "\n"
      pos += 1
    return text

  def fullBuffer(self):
    buf = self.nvim.current.buffer
    return {"type": "full",
      "name": self.relativeFile(),
      "text": self.bufferSlice(buf, 0, len(buf))}

  def bufferFragment(self):
    curRow, curCol = self.nvim.current.window.cursor
    line = curRow - 1
    buf = self.nvim.current.buffer
    minIndent = None
    start = None
    for i in range(max(0, line - 50), line):
      if not re.match(".*\\bfunction\\b", buf[i]): continue
      indent = len(re.match("^\\s*", buf[i]).group(0))
      if minIndent is None or indent <= minIndent:
        minIndent = indent
        start = i

    if start is None: start = max(0, line - 50)
    end = min(len(buf) - 1, line + 20)
    return {"type": "part",
        "name": self.relativeFile(),
        "text": self.bufferSlice(buf, start, end),
        "offsetLines": start}

  def runCommand(self, query, pos=None, fragments=True, silent=False):
    if self.port is None: return
    if isinstance(query, str): query = {"type": query}
    vim = self.nvim
    if (pos is None):
      curRow, curCol = vim.current.window.cursor
      pos = {"line": curRow - 1, "ch": curCol}

    curSeq = vim.eval("undotree()['seq_cur']")
    doc = {"query": query, "files": []}
    if curSeq == vim.eval("b:ternBufferSentAt"):
      fname, sendingFile = (self.relativeFile(), False)
    elif len(self.nvim.current.buffer) > 250 and fragments:
      f = self.bufferFragment()
      doc["files"].append(f)
      pos = {"line": pos["line"] - f["offsetLines"], "ch": pos["ch"]}
      fname, sendingFile = ("#0", False)
    else:
      doc["files"].append(self.fullBuffer())
      fname, sendingFile = ("#0", True)
    query["file"] = fname
    query["end"] = pos
    query["lineCharPositions"] = True

    data = None
    try:
      data = self.makeRequest(doc, silent)
      if data is None: return None
    except:
      pass

    if data is None:
      # check if port is closed
      try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', int(port)))
        if result == 0:
          sock.close()
        else:
          self.start_server()
          if self.port is None: return
          data = self.makeRequest(doc, silent)
          if data is None: return None
      except Exception as e:
        if not silent:
          self.display_error(e)

    if sendingFile and self.nvim.eval("b:ternInsertActive") == "0":
      self.nvim.command("let b:ternBufferSentAt = " + str(curSeq))
    return data

  def sendBuffer(self, files=None):
    if self.port is None: return False
    try:
      tern_makeRequest({"files": files or [self.fullBuffer()]}, True)
      return True
    except:
      return False

  @neovim.function("TernSendBufferIfDirty", sync=True)
  def sendBufferIfDirty(self, args):
    vim = self.nvim
    if (vim.eval("exists('b:ternInsertActive')") == "1" and
        vim.eval("b:ternInsertActive") == "0"):
      curSeq = vim.eval("undotree()['seq_cur']")
      if curSeq > vim.eval("b:ternBufferSentAt") and self.sendBuffer():
        vim.command("let b:ternBufferSentAt = " + str(curSeq))

  def asCompletionIcon(self, type):
    if type is None or type == "?": return "(?)"
    vim = self.nvim
    if type.startswith("fn("):
      if vim.eval("g:tern_show_signature_in_pum") == "0":
        return "(fn)"
      else:
        return type
    if type.startswith("["): return "([])"
    if type == "number": return "(num)"
    if type == "string": return "(str)"
    if type == "bool": return "(bool)"
    return "(obj)"

  def typeDoc(self, rec):
    tp = rec.get("type")
    result = rec.get("doc", " ")
    if tp and tp != "?":
      result = tp + "\n" + result
    return result

  @neovim.function("TernEnsureCompletionCached", sync=True)
  def ensureCompletionCached(self, args):
    vim = self.nvim
    cached = vim.eval("b:ternLastCompletionPos")
    curRow, curCol = vim.current.window.cursor
    curLine = vim.current.buffer[curRow - 1]

    if (curRow == int(cached["row"]) and curCol >= int(cached["end"]) and
      curLine[0:int(cached["end"])] == cached["word"] and
      (not re.match(".*\\W", curLine[int(cached["end"]):curCol]))):
      return

    data = self.runCommand({"type": "completions", "types": True, "docs": True},
      {"line": curRow - 1, "ch": curCol})
    if data is None: return

    completions = []
    for rec in data["completions"]:
      completions.append({"word": rec["name"],
        "menu": self.asCompletionIcon(rec.get("type")),
        "info": self.typeDoc(rec) })
    vim.command("let b:ternLastCompletion = " + json.dumps(completions))
    start, end = (data["start"]["ch"], data["end"]["ch"])
    vim.command("let b:ternLastCompletionPos = " + json.dumps({
      "row": curRow,
      "start": start,
      "end": end,
      "word": curLine[0:end]
    }))

  @neovim.function("TernLookupDocumentation", sync=True)
  def lookupDocumentation(self, args):
    browse = True if args[0] == True else False
    data = self.runCommand("documentation")
    if data is None: return
    doc = data.get("doc")
    url = data.get("url")
    if url:
      if browse:
        savout = os.dup(1)
        os.close(1)
        os.open(os.devnull, os.O_RDWR)
        try:
          result = webbrowser.open(url)
        finally:
          os.dup2(savout, 1)
          return result
      doc = ((doc and doc + "\n\n") or "") + "See " + url
    if doc:
      self.nvim.command("call tern#PreviewInfo(" + json.dumps(doc) + ")")
    else:
      print("no documentation found")

  def echoWrap(self, data, name=""):
    text = data
    if len(name) > 0:
      text = name+": " + text
    col = int(self.nvim.eval("&columns"))-10
    if len(text) > col:
      text = text[0:col]+"..."
    self.echo(text)

  def echo(self, msg):
    self.nvim.command("echo '" + str(msg).replace("'", "''") + "'")

  @neovim.function("TernLookupType", sync=True)
  def lookupType(self, args):
    if self.port is None: return
    data = self.runCommand("type")
    if data: self.echoWrap(data.get("type", ""))

  @neovim.function("TernLookupArgumentHints", sync=True)
  def lookupArgumentHints(self, args):
    fname = args[0]
    apos = args[1]
    if self.port is None: return
    curRow, curCol = self.nvim.current.window.cursor
    data = self.runCommand({"type": "type", "preferFunction": True},
                          {"line": curRow - 1, "ch": apos},
                          True, True)
    if data: self.echoWrap(data.get("type", ""), name=fname)

  @neovim.function("TernLookupDefinition", sync=True)
  def lookupDefinition(self, args):
    if self.port is None: return
    cmd = args[0]
    data = self.runCommand("definition", fragments=False)
    if data is None: return
    vim = self.nvim

    if "file" in data:
      lnum     = data["start"]["line"] + 1
      col      = data["start"]["ch"] + 1
      filename = data["file"]

      if cmd == "edit" and filename == self.relativeFile():
        vim.command("normal! m`")
        vim.command("call cursor(" + str(lnum) + "," + str(col) + ")")
      else:
        vim.command(cmd + " +call\ cursor(" + str(lnum) + "," + str(col) + ") " +
        self.projectFilePath(filename).replace(" ", "\\ "))
    elif "url" in data:
      print("see " + data["url"])
    else:
      print("no definition found")

  def projectFilePath(self, path):
    return os.path.join(self.root, path)

  @neovim.function("TernRefs", sync=True)
  def refs(self, args):
    if self.port is None: return
    vim = self.nvim
    data = self.runCommand("refs", fragments=False)
    if data is None: return
    refs = []
    for ref in data["refs"]:
      lnum     = ref["start"]["line"] + 1
      col      = ref["start"]["ch"] + 1
      filename = self.projectFilePath(ref["file"])
      name     = data["name"]
      text     = vim.eval("getbufline('" + filename + "'," + str(lnum) + ")")
      refs.append({"lnum": lnum,
        "col": col,
        "filename": filename,
        "text": name + " (file not loaded)" if len(text)==0 else text[0]})
    vim.command("call setloclist(0," + json.dumps(refs) + ") | Unite location_list")

  @neovim.function("TernRename", sync=True)
  def rename(self, args):
    if self.port is None: return
    newName = args[0]
    if len(newName) == 0: return
    data = self.runCommand({"type": "rename", "newName": newName}, fragments=False)
    if data is None: return

    vim = self.nvim

    def mycmp(a,b):
      return (cmp(a["file"], b["file"]) or
              cmp(a["start"]["line"], b["start"]["line"]) or
              cmp(a["start"]["ch"], b["start"]["ch"]))

    data["changes"].sort(key=tern_cmp_to_key(mycmp))
    changes_byfile = groupby(data["changes"]
                            ,key=lambda c: self.projectFilePath(c["file"]))

    name = data["name"]
    changes, external = ([], [])
    for file, filechanges in changes_byfile:

      buffer = None
      for buf in vim.buffers:
        if buf.name == file:
          buffer = buf

      if buffer is not None:
        lines = buffer
      else:
        with open(file, "r") as f:
          lines = f.readlines()
      for linenr, linechanges in groupby(filechanges, key=lambda c: c["start"]["line"]):
        text = lines[linenr]
        offset = 0
        changed = []
        for change in linechanges:
          colStart = change["start"]["ch"]
          colEnd = change["end"]["ch"]
          text = text[0:colStart + offset] + newName + text[colEnd + offset:]
          offset += len(newName) - len(name)
          changed.append({"lnum": linenr + 1,
                          "col": colStart + 1 + offset,
                          "filename": file})
        for change in changed:
          if buffer is not None:
            lines[linenr] = change["text"] = text
          else:
            change["text"] = "[not loaded] " + text
            lines[linenr] = text
        changes.extend(changed)
      if buffer is None:
        with open(file, "w") as f:
          f.writelines(lines)
        external.append({"name": file, "text": string.join(lines, ""), "type": "full"})
    if len(external):
      self.sendBuffer(external)
    vim.command("call setloclist(0," + json.dumps(changes) + ") | Unite location_list")
