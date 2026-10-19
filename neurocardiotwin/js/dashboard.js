window.Dashboard=(()=>{
  function setText(selector,text){document.querySelectorAll(selector).forEach(element=>element.textContent=text)}
  async function connection(){
    const indicator=document.querySelector('.sidebar-foot .status-dot');
    try{
      await API.health();
      if(indicator)indicator.className='status-dot';
      setText('#side-backend','Secure workspace online');
    }catch{
      if(indicator)indicator.className='status-dot error';
      setText('#side-backend','Connection unavailable');
    }
  }
  function init(){connection()}
  return{init,connection};
})();
