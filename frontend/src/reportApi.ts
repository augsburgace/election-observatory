import { isPublicMode } from "./publicData";
import { previewPublicReport, publicReportCSV } from "./publicReports";
import { downloadData } from "./api";
import type { ReportPreview, ReportRequest } from './reportTypes';
async function error(response: Response): Promise<never> {
  const body = await response.json().catch(() => ({}));
  const detail = typeof body.detail === 'string' ? body.detail : Array.isArray(body.detail) ? body.detail.map((r:{msg:string})=>r.msg).join('; ') : `Report request failed (${response.status})`;
  throw new Error(detail);
}
export async function previewReport(request:ReportRequest,signal?:AbortSignal):Promise<ReportPreview>{
  if(isPublicMode())return previewPublicReport(request,signal);
  const response=await fetch('/api/v2/reports/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(request),signal});
  if(!response.ok)return error(response);
  return response.json();
}
export async function exportComposedReport(request:ReportRequest,format:string){
  if(isPublicMode()){
    // Open synchronously so an explicit PDF click retains browser popup permission.
    const printWindow=format==='pdf'?window.open('', '_blank'):null;
    try{
      const report=await previewPublicReport(request);
      if(format==='pdf'){
        if(!printWindow)throw new Error('Allow this site to open the printable report, then choose Save as PDF.');
        printWindow.document.open();printWindow.document.write(report.html);printWindow.document.close();
        setTimeout(()=>{if(!printWindow.closed)printWindow.print();},500);
      }else if(format==='html')downloadData(report.html,`observatory-${request.query.state}-r${report.revision}-report.html`,'text/html');
      else if(format==='csv')downloadData(publicReportCSV(report),`observatory-${request.query.state}-r${report.revision}-tables.csv`,'text/csv');
      else if(format==='json')downloadData({...report,request:{...report.request,notes:request.include_notes?request.notes:''}},`observatory-${request.query.state}-r${report.revision}-research.json`);
      else throw new Error('Public reports support HTML, tables CSV, research JSON and browser-print PDF. Full ZIP packaging is available in the local edition.');
      return;
    }catch(error){printWindow?.close();throw error;}
  }
  const response=await fetch(`/api/v2/reports/exports?format=${encodeURIComponent(format)}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(request)});
  if(!response.ok)return error(response);
  const url=URL.createObjectURL(await response.blob());
  const anchor=document.createElement('a');anchor.href=url;anchor.download=`observatory-${request.query.state}-r${request.query.revision??'latest'}-report.${format}`;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
