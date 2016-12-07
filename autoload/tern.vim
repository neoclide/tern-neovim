if !has('python3') | finish | endif

if !exists('g:tern#command')
  let g:tern#command = ["node", expand('<sfile>:h') . '/../node_modules/tern/bin/tern', '--no-port-file']
endif

if !exists('g:tern#arguments')
  let g:tern#arguments = []
endif

let g:tern_job_id = 0
let g:tern_project_root = ''

function! tern#PreviewInfo(info)
  pclose
  new +setlocal\ previewwindow|setlocal\ buftype=nofile|setlocal\ noswapfile|setlocal\ wrap
  exe "normal z" . &previewheight . "\<cr>"
  call append(0, type(a:info)==type("") ? split(a:info, "\n") : a:info)
  wincmd p
endfunction

function! tern#Start()
  call tern#Shutdown()
  let f = findfile('.tern-project', '.;')
  if empty(f) | return | endif
  let g:tern_project_root = fnamemodify(f, ':p:h')
  let command = g:tern#command + g:tern#arguments
  let res = jobstart(command, {
    \ 'cwd': g:tern_project_root,
    \ 'on_stdout': function('s:JobHandler'),
    \ 'on_stderr': function('s:JobHandler'),
    \ 'on_exit': function('s:JobHandler'),
    \ 'detach': 1,
    \})
  if res == 0
    echohl Error | echon 'Invalid arguments: '.command | echohl None
  elseif res == -1
    echohl Error | echon 'Failed to run: '.command | echohl None
  else
    let g:tern_job_id = res
  endif
endfunction

function! tern#Shutdown()
  if !g:tern_job_id | return | endif
  call jobstop(g:tern_job_id)
endfunction

function! s:JobHandler(job_id, data, event)
  if a:event ==# 'stdout'
    for line in a:data
      let list = matchlist(line, '^Listening on port \(\d\+\)')
      if len(list)
        let port = list[1]
        call TernConfig(g:tern_project_root, port)
      " TODO send message to logger
      endif
    endfor
  elseif a:event ==# 'stderr'
    echohl Error | echon 'Tern error: '.join(a:data) | echohl None
  else
    if a:job_id == g:tern_job_id && !v:exiting
      let g:tern_project_root = ''
    endif
  endif
endfunction

function! tern#Complete(findstart, complWord)
  if a:findstart
    call TernEnsureCompletionCached()
    return b:ternLastCompletionPos['start']
  elseif b:ternLastCompletionPos['end'] - b:ternLastCompletionPos['start'] == len(a:complWord)
    return b:ternLastCompletion
  else
    let rest = []
    for entry in b:ternLastCompletion
      if stridx(entry["word"], a:complWord) == 0
        call add(rest, entry)
      endif
    endfor
    return rest
  endif
endfunction

function! tern#LookupArgumentHints()
  if g:tern_show_argument_hints ==# 'no' | return | endif
  let fname = get(matchlist(getline('.')[:col('.')-1],'\([a-zA-Z0-9_]*\)([^()]*$'),1)
  let pos   = match(getline('.')[:col('.')-1],'[a-zA-Z0-9_]*([^()]*$')
  if pos >= 0
    call TernLookupArgumentHints(fname, pos)
  endif
  return ''
endfunction

if !exists('g:tern_show_argument_hints')
  let g:tern_show_argument_hints = 'no'
endif

if !exists('g:tern_show_signature_in_pum')
  let g:tern_show_signature_in_pum = 0
endif

if !exists('g:tern_set_omni_function')
  let g:tern_set_omni_function = 1
endif

if !exists('g:tern_map_keys')
  let g:tern_map_keys = 0
endif

if !exists('g:tern_map_prefix')
  let g:tern_map_prefix = '<LocalLeader>'
endif

if !exists('g:tern_request_timeout')
  let g:tern_request_timeout = 3
endif

function! tern#DefaultKeyMap(...)
  let prefix = len(a:000)==1 ? a:1 : "<LocalLeader>"
  execute 'nnoremap <buffer> '.prefix.'tD' ':TernDoc<CR>'
  execute 'nnoremap <buffer> '.prefix.'tb' ':TernDocBrowse<CR>'
  execute 'nnoremap <buffer> '.prefix.'tt' ':TernType<CR>'
  execute 'nnoremap <buffer> '.prefix.'td' ':TernDef<CR>'
  execute 'nnoremap <buffer> '.prefix.'tpd' ':TernDefPreview<CR>'
  execute 'nnoremap <buffer> '.prefix.'tsd' ':TernDefSplit<CR>'
  execute 'nnoremap <buffer> '.prefix.'ttd' ':TernDefTab<CR>'
  execute 'nnoremap <buffer> '.prefix.'tr' ':TernRefs<CR>'
  execute 'nnoremap <buffer> '.prefix.'tR' ':TernRename<CR>'
endfunction

function! tern#Enable()
  if stridx(&buftype, "nofile") > -1 || stridx(&buftype, "nowrite") > -1
    return
  endif

  command! -buffer TernDoc call TernLookupDocumentation(v:false)
  command! -buffer TernDocBrowse call TernLookupDocumentation(v:true)
  command! -buffer TernType call TernLookupType()
  command! -buffer TernDef call TernLookupDefinition("edit")
  command! -buffer TernDefPreview call TernLookupDefinition("pedit")
  command! -buffer TernDefSplit call TernLookupDefinition("vs")
  command! -buffer TernDefTab call TernLookupDefinition("tabe")
  command! -buffer TernRefs call TernRefs()
  command! -buffer TernRename exe 'call TernRename("'.input("new name? ",expand("<cword>")).'")'

  let b:ternProjectDir = ''
  let b:ternLastCompletion = []
  let b:ternLastCompletionPos = {'row': -1, 'start': 0, 'end': 0}
  if !exists('b:ternBufferSentAt')
    let b:ternBufferSentAt = undotree()['seq_cur']
  endif
  let b:ternInsertActive = 0
  if g:tern_set_omni_function
    setlocal omnifunc=tern#Complete
  endif
  if g:tern_map_keys
    call tern#DefaultKeyMap(g:tern_map_prefix)
  endif
  augroup TernAutoCmd
    autocmd! * <buffer>
    autocmd BufLeave <buffer> :call TernSendBufferIfDirty()
    autocmd CursorHold,CursorHoldI <buffer> call tern#LookupArgumentHints()
    autocmd InsertEnter <buffer> let b:ternInsertActive = 1
    autocmd InsertLeave <buffer> let b:ternInsertActive = 0
  augroup END
endfunction
