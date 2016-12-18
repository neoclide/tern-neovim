if !has('python3') | finish | endif

if !exists('g:tern#command')
  let g:tern#command = ["node", expand('<sfile>:h') . '/../node_modules/tern/bin/tern', '--no-port-file']
endif

if !exists('g:tern#arguments')
  let g:tern#arguments = []
endif

let s:tern_started = 0

function! tern#PreviewInfo(info)
  pclose
  new +setlocal\ previewwindow|setlocal\ buftype=nofile|setlocal\ noswapfile|setlocal\ wrap
  exe "normal z" . &previewheight . "\<cr>"
  call append(0, type(a:info)==type("") ? split(a:info, "\n") : a:info)
  wincmd p
endfunction

function! tern#Complete(findstart, complWord) abort
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

function! tern#LookupArgumentHints() abort
  if g:tern_show_argument_hints ==# 'no' | return | endif
  let c = mode() ==# 'i' ? col('.')  - 2 : col('.') - 1
  let fname = get(matchlist(getline('.')[:c],'\([a-zA-Z0-9_]*\)([^()]*$'),1)
  let pos   = match(getline('.')[:c],'[a-zA-Z0-9_]*([^()]*$')
  if pos >= 0
    call TernLookupArgumentHints(fname, pos)
  endif
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

function! tern#Enable() abort
  if get(s:, 'tern_started', 0) == 0
    call TernStart()
    let s:tern_started = 1
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
    autocmd!
    autocmd BufLeave <buffer> :call TernSendBufferIfDirty()
    autocmd CursorHold,CursorHoldI  <buffer> :call tern#LookupArgumentHints()
    autocmd InsertEnter <buffer> let b:ternInsertActive = 1
    autocmd InsertLeave <buffer> let b:ternInsertActive = 0
  augroup END
endfunction
