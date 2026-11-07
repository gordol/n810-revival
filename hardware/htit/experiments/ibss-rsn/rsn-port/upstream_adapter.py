"""Small checked upstream integration hook; no cryptographic algorithm changes."""
def add_driver_sequence_callback(path):
    text=path.read_text()
    anchor='static int ibss_rsn_auth_init_group('
    callback='\t\t.set_key = auth_set_key,\n'
    if text.count(anchor)!=1 or text.count(callback)!=1:
        raise ValueError('Pinned IBSS RSN callback layout changed')
    hook="""extern int pocket_rsn_get_seqnum(struct wpa_supplicant*,int,u8*);
static int auth_get_seqnum(void* ctx,const u8* addr,int index,u8* seq)
{
    struct ibss_rsn* rsn=ctx;
    if(addr)return -1;
    return pocket_rsn_get_seqnum(rsn->wpa_s,index,seq);
}

"""
    path.write_text(text.replace(anchor,hook+anchor).replace(callback,callback+'\t\t.get_seqnum = auth_get_seqnum,\n'))
