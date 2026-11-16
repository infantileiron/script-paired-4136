/** @typedef {{id:number,code:string,team:string,before:number|null,after:number|null,note:string}} Pair */
/** @typedef {{id:number,name:string,team:string,state:string,result:object,error:string}} Evaluation */
/** @typedef {{id:number,evaluation_id:number,decision:string,note:string,status:string}} Adoption */
/** @typedef {{id:number,evaluation_id:number,name:string,state:'pending'|'downloadable'|'failed',roster:string[],lower:number,upper:number,epsilon:number,artifact_path:string,result:object|null,error:string,attempts:number,created:string,updated:string}} AnonRelease */
/** @typedef {{consultant_code:string,total_epsilon:number,spent_epsilon:number,remaining_epsilon:number}} PrivacyAccount */
/** @typedef {{total_epsilon_cap:number,accounts:PrivacyAccount[],releases:AnonRelease[]}} BudgetOverview */
/** @typedef {{mechanism:string,adjacency:string,n:number,lower:number,upper:number,sensitivity:number,epsilon:number,delta:number,noise_scale_b:number,noisy_mean:number,release_id:number,evaluation_id:number,name:string,roster_size:number,created:string,published_at:string,note:string}} PublicRelease */
