export async function api(path, options={}) {
  const csrf=document.querySelector('[name=csrfmiddlewaretoken]')?.value;
  const isFormData=typeof FormData!=='undefined'&&options.body instanceof FormData;
  const headers={'Accept':'application/json',...(options.body&&!isFormData?{'Content-Type':'application/json'}:{}),...(csrf?{'X-CSRFToken':csrf}:{}),...(options.headers||{})};
  const response=await fetch(path,{credentials:'same-origin',...options,headers});
  if(!response.ok){let message=`Request failed (${response.status})`;try{message=(await response.json()).error||message}catch{} throw new Error(message)}
  const type=response.headers.get('content-type')||'';return type.includes('application/json')?response.json():response;
}
export const send=(path,data)=>api(path,{method:'POST',body:typeof FormData!=='undefined'&&data instanceof FormData?data:JSON.stringify(data)});
