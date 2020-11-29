#if !FA2_INTERFACE
#define FA2_INTERFACE

type fa2_token_id = nat;


type mint_burn_tx = 
[@layout:comb]
{
  owner : address,
  token_id : fa2_token_id,
  amount : nat
}

type mint_burn_tokens_param = list(mint_burn_tx)

type token_metadata =
[@layout:comb]
{
  token_id : fa2_token_id,
  symbol : string,
  name : string,
  decimals : nat,
  extras : map(string, string),
}

type token_manager =
    Create_token (token_metadata)
  | Mint_tokens (mint_burn_tokens_param)
  | Burn_tokens (mint_burn_tokens_param)
;

type token_admin = 
   Set_admin (address)
  | Confirm_admin 
  | Pause (bool)
;

#endif