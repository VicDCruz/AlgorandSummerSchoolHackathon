from algosdk import transaction, account
import algosdk
from algosdk.v2client import *
from pyteal import *
from beaker import *
from beaker import sandbox
from beaker.client import ApplicationClient
from algosdk.transaction import *
from base64 import b64decode
from algosdk.logic import *
from algosdk import constants
import unittest
from algosdk.kmd import KMDClient
import time


APPROVAL_SRC = os.path.join('contracts', "ApprovalProgram.teal")
CLEARSTATE_SRC = os.path.join('contracts', "ClearStateProgram.teal")


def compileTEAL(client, code):
    compile_response = client.compile(code)
    return b64decode(compile_response['result'])


def fundApp(client, sender: sandbox.SandboxAccount, AppAddr: str, Ammount):
    txn = transaction.PaymentTxn(sender.address, sp=client.suggested_params(), receiver=AppAddr, amt=Ammount)
    signedTxn = txn.sign(sender.private_key)
    txid = client.send_transaction(signedTxn)
    wait_for_confirmation(client, signedTxn.get_txid())


def DeployAndFundApp():
    # account sender
    client = sandbox.get_algod_client()
    accounts = sandbox.get_accounts()

    sender = accounts[0]

    with open(APPROVAL_SRC, "r", encoding="utf-8") as f:
        approval_program = f.read()
    with open(CLEARSTATE_SRC, "r", encoding="utf-8") as f:
        clear_program = f.read()

    global_schema = StateSchema(num_uints=2, num_byte_slices=1)
    local_schema = StateSchema(num_uints=4, num_byte_slices=0)

    txn = ApplicationCreateTxn(
        sender=sender.address,
        sp=client.suggested_params(),
        on_complete=OnComplete.NoOpOC.real,
        approval_program=compileTEAL(client, approval_program),
        clear_program=compileTEAL(client, clear_program),
        app_args=[],
        global_schema=global_schema,
        local_schema=local_schema)

    signedTxn = txn.sign(sender.private_key)
    txid = client.send_transaction(signedTxn)
    response = wait_for_confirmation(client, txid)
    CreatedAppID = response["application-index"]

    fundApp(client, sender, get_application_address(CreatedAppID), 100000000000)

    # already funded, now setup
    txn = ApplicationCallTxn(
        sender=sender.address,
        index = CreatedAppID,
        sp=client.suggested_params(),
        on_complete=OnComplete.NoOpOC.real,
        app_args=["setup"],
        boxes=[(0,0), (0,0), (0,0), (0,0), (0,0), (0,0), (0, str.encode("MONSTERS")), (0, 0)])

    signedTxn = txn.sign(sender.private_key)
    txid = client.send_transaction(signedTxn)
    wait_for_confirmation(client, txid)

    return CreatedAppID


def getActiveMonstersList(AppID):
    client = sandbox.get_algod_client()
    boxData = b64decode(client.application_box_by_name(AppID, str.encode("MONSTERS"))["value"])

    len = int.from_bytes(boxData[0:8])

    outList = []
    for i in range(8,len*32+8,32):
        outList.append((int.from_bytes(boxData[i:i+8]), int.from_bytes(boxData[i+8:i+16]), int.from_bytes(boxData[i+16:i+24])))

    return outList


def addMonster(AppID, pos_x, pos_y):
    client = sandbox.get_algod_client()
    accounts = sandbox.get_accounts()
    sender = accounts[0]

    sp = client.suggested_params()
    sp.fee = constants.MIN_TXN_FEE * 2
    sp.flat_fee = True

    txn = ApplicationCallTxn(
        sender=sender.address,
        index=AppID,
        sp=sp,
        on_complete=OnComplete.NoOpOC.real,
        app_args=["addMonster", pos_x, pos_y],
        boxes=[(0,0), (0,0), (0,0), (0, str.encode("MONSTERS"))]
    )

    signed_txn = txn.sign(sender.private_key)
    client.send_transaction(signed_txn)

    txnOut = wait_for_confirmation(client, txn.get_txid())
    return txnOut


def enterPlayer(AppID, playerAccount:sandbox.SandboxAccount):
    client = sandbox.get_algod_client()
    
    sp = client.suggested_params()
    sp.fee = constants.MIN_TXN_FEE * 2
    sp.flat_fee = True

    senderAddr = algosdk.encoding.decode_address(playerAccount.address)
    
    txn = ApplicationCallTxn(
        sender=playerAccount.address,
        index=AppID,
        sp=sp,
        on_complete=OnComplete.OptInOC.real,
        app_args=["enterPlayer"],
        boxes=[(0, senderAddr)]
    )
    
    signed_txn = txn.sign(playerAccount.private_key)
    client.send_transaction(signed_txn)

    wait_for_confirmation(client, txn.get_txid())


def exitAndSavePlayer(AppID, playerAccount:sandbox.SandboxAccount):
    client = sandbox.get_algod_client()
    
    sp = client.suggested_params()
    sp.fee = constants.MIN_TXN_FEE * 2
    sp.flat_fee = True

    senderAddr = algosdk.encoding.decode_address(playerAccount.address)
    
    txn = ApplicationCallTxn(
        sender=playerAccount.address,
        index=AppID,
        sp=sp,
        on_complete=OnComplete.NoOpOC.real,
        app_args=["exitAndSavePlayer"],
        boxes=[(0, senderAddr)]
    )

    signed_txn = txn.sign(playerAccount.private_key)
    client.send_transaction(signed_txn)

    wait_for_confirmation(client, txn.get_txid())


def playerMove(AppID, playerAccount:sandbox.SandboxAccount, dir:str):
    client = sandbox.get_algod_client()
    
    txn = ApplicationCallTxn(
        sender=playerAccount.address,
        index=AppID,
        sp=client.suggested_params(),
        on_complete=OnComplete.NoOpOC.real,
        app_args=["playerMove", dir])
    
    signed_txn = txn.sign(playerAccount.private_key)
    client.send_transaction(signed_txn)

    wait_for_confirmation(client, txn.get_txid())


def playerKillMonster(AppID, playerAccount:sandbox.SandboxAccount, monsterASAID):
    client = sandbox.get_algod_client()
    
    sp = client.suggested_params()
    sp.fee = constants.MIN_TXN_FEE * 2
    sp.flat_fee = True

    txn1 = AssetOptInTxn(playerAccount.address, sp=client.suggested_params(), index=monsterASAID)
    txn2 = ApplicationCallTxn(
        sender=playerAccount.address,
        index=AppID,
        sp=sp,
        on_complete=OnComplete.NoOpOC.real,
        app_args=["playerKillMonster"],
        boxes=[(0,0), (0,0), (0,0), (0, algosdk.encoding.decode_address(playerAccount.address)), (0, "MONSTERS")],
        foreign_assets=[monsterASAID]
    )

    txn_list = [txn1, txn2]
    gid = transaction.calculate_group_id(txn_list)
    for t in txn_list:
        t.group = gid

    signedTxnList = [t.sign(playerAccount.private_key) for t in txn_list]
    client.send_transactions(signedTxnList)

    for t in signedTxnList:
        wait_for_confirmation(client, t.get_txid())
    # wait_for_confirmation(client, txn1.get_txid())
    # return wait_for_confirmation(client, txn2.get_txid())


def secureAsset(AppID, playerAccount:sandbox.SandboxAccount):
    client = sandbox.clients.get_algod_client()
    playerLocalState = sandbox.clients.get_indexer_client().lookup_account_application_local_state(playerAccount.address, application_id=AppID)
    
    monsterASAID = playerLocalState["UNSECURED_ASSET"]
    if (monsterASAID == 0):
        return
    
    sp = client.suggested_params()
    sp.fee = constants.MIN_TXN_FEE * 2
    sp.flat_fee = True
    
    txn = ApplicationCallTxn(
        sender=playerAccount.address,
        index=AppID,
        sp=sp,
        on_complete=OnComplete.NoOpOC.real,
        app_args=["secureAsset"],
        foreign_assets=[monsterASAID]
    )


def playerSteal(AppID, thiefAccount:sandbox.SandboxAccount, victimAddress:str):
    client = sandbox.clients.get_algod_client()
    victimLocalState = sandbox.clients.get_indexer_client().lookup_account_application_local_state(victimAddress, application_id=AppID)

    print(victimLocalState)
    
    ASAToSteal = victimLocalState["UNSECURED_ASSET"]
    if ASAToSteal == 0:
        return

    sp = client.suggested_params()
    sp.fee = constants.MIN_TXN_FEE * 2
    sp.flat_fee = True

    txn1 = AssetOptInTxn(thiefAccount.address, sp=client.suggested_params(), index=ASAToSteal)
    txn2 = ApplicationCallTxn(
        sender=thiefAccount.address,
        index=AppID,
        sp=sp,
        on_complete=OnComplete.OptInOC.real,
        app_args=["pvpSteal"],
        accounts = [victimAddress],
        foreign_assets=[ASAToSteal]
    )

    txn_list = [txn1, txn2]
    gid = transaction.calculate_group_id(txn_list)
    for t in txn_list:
        t.group = gid

    signedTxnList = [t.sign(thiefAccount.private_key) for t in txn_list]
    client.send_transactions(signedTxnList)
    
    for t in signedTxnList:
        wait_for_confirmation(client, t.get_txid())




class MonsterArenaTestCommon(unittest.TestCase):
    AppID = None
    ActiveMonsters = []
    ActivePlayers = []
    ActivePlayers_localState = []

    @classmethod
    def getMonsterBoxContents(self):
        idxClient = sandbox.get_indexer_client()
        monsterBox = idxClient.application_box_by_name(self.AppID, bytes("MONSTERS", encoding="utf-8"))
        monsterBox = b64decode(monsterBox['value'])
        
        liveMonsters = []
        monsterLen = int.from_bytes(monsterBox[:8], byteorder='big')
        for i in range (0,monsterLen):
            pos_x = int.from_bytes(monsterBox[8+i*24:8+i*24+8], byteorder='big')
            pos_y = int.from_bytes(monsterBox[8+i*24+8:8+i*24+16], byteorder='big')
            ASAID = int.from_bytes(monsterBox[8+i*24+16:8+i*24+24], byteorder='big')
            
            liveMonsters.append({"POS_X":pos_x, "POS_Y":pos_y, "ASA_ID":ASAID})
        return liveMonsters
    
    
    @classmethod
    def playerBoxToDict(self, boxContent, boxName):
        boxContent = b64decode(boxContent['value'])
        playerVal = {"ADDRESS": boxName,
                    "POS_X": int.from_bytes(boxContent[:8], "big"), 
                     "POS_Y": int.from_bytes(boxContent[8:16], "big"), 
                     "SCORE": int.from_bytes(boxContent[16:24], "big"), 
                     "UNSECURED_ASSET": int.from_bytes(boxContent[24:32], "big")}
        return playerVal


    @classmethod
    def getPlayerBox(self, account:sandbox.SandboxAccount):
        idxClient = sandbox.get_indexer_client()
        boxName = algosdk.encoding.decode_address(account.address)
        boxContent = idxClient.application_box_by_name(self.AppID, boxName)
        return self.playerBoxToDict(boxContent, boxName)
    

    @classmethod
    def getPlayerBoxesContents(self):
        idxClient = sandbox.get_indexer_client()
        playerBoxes = idxClient.application_boxes(self.AppID)["boxes"]
        
        playerBoxes = [b64decode(k["name"]) for k in playerBoxes if b64decode(k["name"]) != bytes("MONSTERS", encoding="utf-8")]

        livePlayers=[]
        for boxName in playerBoxes:
            boxContent = idxClient.application_box_by_name(self.AppID, boxName)
            livePlayers.append(self.playerBoxToDict(boxContent, boxName))
        return livePlayers
    
        
    @classmethod
    def getPlayerLocalState(self, account:sandbox.SandboxAccount):
        p = sandbox.get_algod_client().account_application_info(account.address, self.AppID)["app-local-state"]['key-value']
        for v in p:
            if (v["key"] == 'UE9TX1k='):
                POS_X = v["value"]["uint"]
            elif (v["key"] == 'UE9TX1g='):
                POS_Y = v["value"]["uint"]
            elif (v["key"] == 'VU5TRUNVUkVEX0FTU0VU'):
                ASA = v["value"]["uint"]
            elif (v["key"] == "U0NPUkU="):
                Score = v["value"]["uint"]
        
        val = {"POS_X":POS_X, "POS_Y":POS_Y, "SCORE": Score, "UNSECURED_ASSET": ASA}
        return val



    
class AllTests(MonsterArenaTestCommon):
    
    @classmethod
    def test_AddMonsters(self, n=6):
        pos = [(x,y) for x,y in enumerate(range(0,n))]
        for x,y in pos:
            try:
                txnOut = addMonster(self.AppID, x, y)
            except:
                assert False, "Unable to add one of the monsters"
            
            ASA_ID = txnOut["inner-txns"][0]["asset-index"]
            self.ActiveMonsters.append({"POS_X":x, "POS_Y":y, "ASA_ID":ASA_ID})
        
        time.sleep(10)
        
        liveMonsters = self.getMonsterBoxContents()
        diff = [i for i in liveMonsters + self.ActiveMonsters if i not in liveMonsters or i not in self.ActiveMonsters]
        assert len(diff) == 0, "Monsters in blockchain =/= monsters supposedly added"
        
        
    @classmethod
    def test_AddPlayers(self):
        for acc in sandbox.get_accounts():
            try:
                txnOut = enterPlayer(self.AppID, acc)
            except:
                assert False, "Unable to add one of the players"
            self.ActivePlayers.append({"ADDRESS":algosdk.encoding.decode_address(acc.address),
                                       "POS_X": 0, "POS_Y": 0, 
                                       "SCORE": 0, "UNSECURED_ASSET": 0})
            self.ActivePlayers_localState.append({algosdk.encoding.decode_address(acc.address):{
                                       "POS_X": 0, "POS_Y": 0, 
                                       "SCORE": 1, "UNSECURED_ASSET": 0}})
        
        time.sleep(10)
        livePlayers = self.getPlayerBoxesContents()
        
        diff = [i for i in livePlayers + self.ActivePlayers if i not in livePlayers or i not in self.ActivePlayers]
        assert len(diff) == 0, "Players actually in blockchain =/= players supposedly added"
        
    
    @classmethod
    def test_MonsterASAs(self):
        AppAddress = get_application_address(self.AppID)
        for m in self.ActiveMonsters:
            try:
                assetInfo = sandbox.get_algod_client().asset_info(m["ASA_ID"])
                assert assetInfo["params"]["clawback"] == AppAddress, "Clawback address incorrect"
                assert assetInfo["params"]["freeze"] == AppAddress, "Freeze address incorrect"
                assert assetInfo["params"]["manager"] == AppAddress, "Manager address incorrect"
            except:
                assert False, "Asset not minted correctly"


    @classmethod
    def test_playerKillMonster(self):
        monsterIdx = 0
        for acc in sandbox.get_accounts():
            try:
                cachedLocalVal = self.getPlayerLocalState(acc)
                monsterToErase = self.ActiveMonsters[monsterIdx]
                out = playerKillMonster(self.AppID, acc, self.ActiveMonsters[monsterIdx]["ASA_ID"])
            except:
                assert False, "Monster kill failed (or maybe account not opted in correctly)"

            self.ActiveMonsters[monsterIdx] = self.ActiveMonsters[-1]
            self.ActiveMonsters.pop()
            
            #indexer not up to date bug
            time.sleep(10)
            
            liveMonsters = self.getMonsterBoxContents()
            diff = [i for i in liveMonsters + self.ActiveMonsters if i not in liveMonsters or i not in self.ActiveMonsters]
            assert len(diff) == 0, "monsters in blockchain =/= monsters off chain"

            # check local state of player to see they got the ASA
            localVal = self.getPlayerLocalState(acc)
            
            assert localVal["SCORE"] == cachedLocalVal["SCORE"] + 1, "Score not updated when killing monster"
            assert localVal["UNSECURED_ASSET"] == monsterToErase["ASA_ID"], "ASA not appropriated correctly"

            #check asset is owned by account
            balances = sandbox.get_indexer_client().asset_balances(monsterToErase["ASA_ID"])
            for b in balances["balances"]:
                if (b["address"] == get_application_address(self.AppID)):
                    assert b["amount"] == 0, "contract should not have the asset"
                elif b["address"] == acc.address:
                    assert b["amount"] == 1, "account should have the asset now"




if __name__ == "__main__":
    try:
        AppID = DeployAndFundApp()
    except:
        assert False, "Failed to deploy and fund contract. Possibly has syntax bugs"
    print("APP DEPLOYED AND FUNDED CORRECTLY WITH ID ", AppID)
    
    AllTests.AppID = AppID
    unittest.main()