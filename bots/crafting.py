"""Ordinary legacy combination workflow; initial verified recipe data is 2092.

PlayerWork wire layout is verified at ZoneServer 0x76ee00: i32 recipe, two
i16 arguments, three counted i16 vectors and two counted u32 vectors. The
combine operation consumes the first two vectors as inventory bags and slots.
"""
import asyncio
import struct
import time
from wire import ProtocolError


# S_Combine: output column 6, amount 8, success 9, ingredient triples 10..21.
# 134: alloy+stone -> core. 137: core+quest ring -> finished trophy.
RECIPES = {30708:(134,(30702,30703)),30714:(137,(30708,30711))}


def work_payload(recipe, locations):
    if recipe not in (134,137) or len(locations)!=2 or len(set(locations))!=2:
        raise ProtocolError('Unverified combination recipe or duplicate material slot')
    bags,slots=zip(*locations)
    if any(not 0<=bag<=16 or not 0<=slot<256 for bag,slot in locations):
        raise ProtocolError('Invalid combination material location')
    return (struct.pack('<ihhH',recipe,1,0,2)+struct.pack('<2h',*bags)+
            struct.pack('<H2h',2,*slots)+struct.pack('<HHH',0,0,0))


async def ensure(ctx, output, depth=0):
    await ctx.inventory.refresh(ctx.send)
    if ctx.inventory.first(output) is not None:
        return
    if depth>2 or output not in RECIPES:
        raise ProtocolError(f'Crafting requires an owned ingredient {output}')
    recipe,ingredients=RECIPES[output]
    for ident in ingredients:
        if ctx.inventory.first(ident) is None:
            await ensure(ctx,ident,depth+1)
    locations=[ctx.inventory.require(i) for i in ingredients]
    await ctx.send('LeaveShop',b'')
    await ctx.send('TalkToNPC',struct.pack('<I',0))
    ctx.session.buffers['EnterStrengthen']=[]
    # SimpleAction jump-table entry 14 creates CCombineOp (operation 39), then
    # emits EnterStrengthen(0,10). EnterWorks is unrelated production history.
    await ctx.send('PlayerAction',struct.pack('<BIIIH',14,0,0,0,0))
    enter=await ctx.session.expect('EnterStrengthen',timeout=8)
    if len(enter)!=6 or struct.unpack('<Ih',enter)!=(0,10):
        raise ProtocolError('Unexpected native combination window layout')
    ctx.report(f'Crafting: opened native combination window for recipe {recipe}.',flush=True)
    await ctx.send('PlayerWork',work_payload(recipe,locations))
    deadline=time.monotonic()+25
    while ctx.inventory.first(output) is None and time.monotonic()<deadline:
        await asyncio.sleep(.2)
    await ctx.inventory.refresh(ctx.send)
    if ctx.inventory.first(output) is None:
        raise ProtocolError(f'Crafting recipe {recipe} did not produce owned item {output}')
    ctx.report(f'Crafting: native inventory confirmed recipe {recipe} produced item {output}.',flush=True)


async def craft_then_equip(ctx,step):
    if ctx.quest.id!=2092 or step.args[0]!=30714:
        raise ProtocolError('Craft/equip semantics are verified only for the refining tutorial')
    # Avoid recrafting on reconnect if the trophy is already equipped.
    from item_stream import equipment
    await ctx.send('EnterNodeEquipAndSpell',b'')
    raw=await ctx.session.expect('EnterNodeEquipAndSpell',timeout=8)
    worn,_=equipment(raw)
    if any(page==0 and item.id==30714 for (page,_),item in worn.items()):
        return
    await ensure(ctx,30714)
    from objectives import drive_equip
    await drive_equip(ctx,step)
