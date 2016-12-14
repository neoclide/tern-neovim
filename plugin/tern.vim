if !has('nvim') | finish | endif

augroup tern
  autocmd!
  autocmd VimEnter * call tern#Start()
augroup end
