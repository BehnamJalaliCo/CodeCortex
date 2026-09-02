export type Json=Record<string,unknown>
export class CodeCortexHttpError extends Error{constructor(public status:number,public detail:unknown){super(`CodeCortex API ${status}: ${String(detail)}`)}}
export class CodeCortexClient{
  constructor(public baseUrl='http://127.0.0.1:7340',public token?:string,public apiVersion='v1'){}
  private async request<T>(method:string,path:string,body?:unknown):Promise<T>{const headers:Record<string,string>={Accept:'application/json'};if(this.token)headers.Authorization=`Bearer ${this.token}`;if(body!==undefined)headers['Content-Type']='application/json';const response=await fetch(`${this.baseUrl.replace(/\/$/,'')}/api/${this.apiVersion}/${path.replace(/^\//,'')}`,{method,headers,body:body===undefined?undefined:JSON.stringify(body)});const payload=response.status===204?null:await response.json();if(!response.ok)throw new CodeCortexHttpError(response.status,(payload as any)?.detail??payload);return payload as T}
  health(){return this.request<Json>('GET','health')}
  repositories(){return this.request<Json[]>('GET','repositories')}
  overview(repositoryId:string){return this.request<Json>('GET',`repositories/${encodeURIComponent(repositoryId)}/overview`)}
  search(repositoryId:string,query:string,limit=20){return this.request<Json>('POST',`repositories/${encodeURIComponent(repositoryId)}/search`,{query,limit})}
  context(repositoryId:string,query:string,budget=32000){return this.request<Json>('POST',`repositories/${encodeURIComponent(repositoryId)}/context`,{query,budget})}
  impact(repositoryId:string,query:string){return this.request<Json>('POST',`repositories/${encodeURIComponent(repositoryId)}/impact`,{query})}
  prAnalysis(repositoryId:string,baseRef:string,headRef='HEAD'){return this.request<Json>('POST',`repositories/${encodeURIComponent(repositoryId)}/pr-analysis`,{base_ref:baseRef,head_ref:headRef})}
}
