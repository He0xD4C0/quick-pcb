"""Real stdio MCP read against the authorized fixture; no Codex restart."""
import asyncio,json,sys
from eda_session import session,R
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
async def main():
 _,window=session()
 repo=R.parents[1]
 params=StdioServerParameters(command=str(repo/'mcp-server/.venv/bin/python'),args=['-m','boardspec_mcp.schematic_entry'],cwd=str(repo/'mcp-server'))
 async with stdio_client(params) as (read,write):
  async with ClientSession(read,write) as client:
   await client.initialize()
   result=await client.call_tool('get_schematic_violations',{'window_id':window})
   raw=result.model_dump(mode='json',by_alias=True)
   (R/'evidence/eda/mcp-stdio-diagnostics.json').write_text(json.dumps(raw,indent=2)+'\n')
   data=raw.get('structuredContent')
   assert data and data['ok'] and data['passed'] is False,raw
   assert len(data['violations'])==4,data
   assert all(row['objects'] and row['type']=='EDA_DRC_LOG' for row in data['violations'])
   print(json.dumps({'isError':raw.get('isError'),'passed':data['passed'],'violations':len(data['violations']),'structuredContent':True}))
asyncio.run(main())
