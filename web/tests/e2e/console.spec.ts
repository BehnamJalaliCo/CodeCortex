import {expect,test} from '@playwright/test'

const repository={repository_id:'repo-1',workspace:'main',name:'CodeCortex',root:'/workspace',created_at:new Date().toISOString()}
const overview={repository:{root:'/workspace',languages:[]},index:{tracked:100,files_reparsed:0,duration_ms:12},graph:{nodes:500,edges:900,symbols:300},git:{commits:42,hot_files:['src/app.py']},runtime:{health:{repository:true,symbols:true},active_backends:[]}}

test.beforeEach(async({page})=>{
  await page.route('**/api/v1/**',route=>{
    const url=new URL(route.request().url())
    if(url.pathname==='/api/v1/health')return route.fulfill({json:{status:'ok',version:'v1'}})
    if(url.pathname==='/api/v1/repositories')return route.fulfill({json:[repository]})
    if(url.pathname==='/api/v1/repositories/repo-1/overview')return route.fulfill({json:overview})
    return route.fulfill({status:404,json:{detail:'not mocked in console smoke test'}})
  })
})

test('renders the control plane and selected repository',async({page})=>{
  await page.goto('/')
  await expect(page.getByRole('heading',{name:'Console'})).toBeVisible()
  await expect(page.getByLabel('Repository')).toHaveValue('repo-1')
  await expect(page.getByText('Indexed files')).toBeVisible()
  await expect(page.getByText('CodeCortex',{exact:true}).first()).toBeVisible()
})
