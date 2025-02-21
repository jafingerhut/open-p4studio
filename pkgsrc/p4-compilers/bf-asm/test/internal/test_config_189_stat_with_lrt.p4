
/* Sample P4 program */
header_type pkt_t {
    fields {
        srcAddr : 32;
        dstAddr : 32;
        protocol : 8;
        srcPort : 16;
        dstPort : 16;
        
        a : 32;
        b : 32;
        c : 32;
        d : 32;
    }
}

parser start {
    return parse_ethernet;
}

header pkt_t pkt;

parser parse_ethernet {
    extract(pkt);
    return ingress;
}


action action_0(param0, param1, param2, param3, param4){
    modify_field(pkt.a, param0);
}

action nop(){
}

@pragma lrt_enable 1
counter counter_0 {
   type: packets;
   direct: table_0;
   min_width: 32;
}

@pragma immediate 0
table table_0 {
    reads {                                                                     
        pkt.srcPort   : exact;                                                  
        pkt.dstPort   : ternary;
    }                                                                           
    actions {                                                                   
        nop;                                                                    
        action_0;
    }                                                                           
    size : 4096;
}     


/* Main control flow */

control ingress {
      apply(table_0);
}
