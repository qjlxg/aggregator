# w1770946466 北慕白  https://github.com/w1770946466/Auto_proxy
# v2ray_collecto
# coding=utf-8
import base64
import requests
import re
import time
import os
import threading
from tqdm import tqdm
import random, string
import datetime
from time import sleep
import chardet

#试用机场链接
home_urls =(
'https://37cdn.ski9.cn',
'http://vpn1.fengniaocloud.top',
'http://vpn1.fnvpn.top',
'https://abc.wisky.lat',
'http://subuu.xfxvpn.me',
'https://sub.juejie.store',
'https://www.zygcloud.net',
'https://www.zygcloud.com',
'https://link.sunsun.icu',
'http://vpn.bigbears.top',
'http://daxiongyun.net',
'https://liuliugoo.755r.cn',
'https://by1.liuliugo.cfd',
'https://by2.liuliugo.cfd',
'https://sub.skrspc.org',
'https://api.skrspc.org',
'https://3by.liuliugo.cfd',
'https://www.songbug.cloud',
'https://dobcloud.com',
'https://hn1r5k7322.bitmusttw.com',
'http://uuvpn.me',
'https://yun.dashiba.com',
'https://5gsieutoc.fun',
'https://app.1130.net',
'https://panel.darkbaz.com',
'https://full.kddi.best',
'https://ikanned.com:12000',
'https://apanel.allbatech.net',
'https://abbabav2board.foxspirit.vip',
'https://xunyungogogo.xyz',
'https://www.kuaidianlianjienode.sbs',
'https://20242024.dilala.xyz',
'https://yhl.yinghuas.sbs',
'https://api-hd.hd-yun.cn',
'https://cc.drchi.icu',
'https://rioo.nai99.top',
'https://kog.nai99.top',
'https://kk.nai99.top',
'https://api.hd-yun.cn',
'https://joo.nai99.top',
'https://hd-yun.cn',
'http://sub11.xn--54qu5qypuo1o.xn--fiqs8s',
'http://gtacdnsub.work',
'https://v2s.ip-ddns.com',
'https://api.heima4u.com',
'https://api.heima2u.com',
'http://b.outwall.top',
'https://bitfat.top',
'https://cn.ptss.me',
'https://auracdn.fastappss.com',
'https://old-v2b.linkedton.com',
'https://v2.gpket.net',
'https://api.quicss.com',
'https://www.jiandanyun.xyz',
'https://jiandanyun.xyz',
'https://jd.233235.xyz',
'https://jd.170203.xyz',
'https://huawei.xhjvpn.cn',
'https://my.mgcores.com',
'https://g15311cec.cdn.uunode.com',
'https://proxy.tizishangwang.xyz',
'https://loopp.bigdog.click',
'http://111.173.106.156:8899',
'http://139.162.31.189:7022',
'http://175.178.9.20',
'http://258936.xyz',
'http://47.101.67.199:6699',
'http://47.122.132.169:23411',
'http://47.122.55.225:50001',
'http://47.74.1.114:8089',
'http://51.255.173.39',
'http://a.tiantian2024.top',
'http://a.tiantian2024.xyz',
'http://a.xinghongyun.top',
'http://aa.bxox.cc',
'http://ab.bxox.cc',
'http://apanel.allbatech.net',
'http://api.mlxsj.top',
'http://b.tiantian2024.top',
'http://b.tiantian2024.xyz',
'http://b.xinghongyun.top',
'http://banshanzhu.com',
'http://bobapp.xuebispeed.com',
'http://changyouVPN.top',
'http://deepquery.cn',
'http://fast.thenight.icu',
'http://fly.6128888.xyz',
'http://gta99.cc',
'http://gtacloud.cc',
'http://huojian2.xyz',
'http://kuailejc.xyz',
'http://m2.bxoxx.xyz',
'http://mbox.idsduf.com',
'http://mbxx.zhunchuanpb.com',
'http://na.bxox.cc',
'http://nuxyun.v2rayflash.top',
'http://pa.bxoxx.xyz',
'http://panel.moon2046.com',
'http://pay.xinghongpay.top',
'http://po1.6128888.xyz',
'http://po2.6128888.xyz',
'http://po3.6128888.xyz',
'http://putao.i2345.me',
'http://putao.i2345.org',
'http://southsidelife.tryme3.xyz',
'http://sub.kjdjakskl.cyou',
'http://subxfxssr.xfxvpn.me',
'http://suliannet.cn',
'http://supercloud666.link',
'http://tiantian2024.xyz',
'http://tt.yesiamai.com',
'http://v.moon2046.com',
'http://v02.520131.best',
'http://v2.demianred.com',
'http://vpn.gangko.cn',
'http://web.nnpy.org',
'http://web.yoyokid.win',
'http://webc.yoogroup.uk',
'http://wuxianjc.top',
'http://www.258936.xyz',
'http://www.huojian2.xyz',
'http://www.tiantian2024.xyz',
'http://x2b.eans.top',
'http://xb.718181.xyz',
'http://xueyejiasu.com',
'http://yl.hq12.top',
'http://ywl.201593.xyz',
'https://01.conva.top',
'https://0run.vip',
'https://1.dishuyun.top',
'https://1.vyunyun.top',
'https://106.54.49.22',
'https://111.xiyouji.tk',
'https://154.17.13.104',
'https://154.17.15.126',
'https://154.21.81.177',
'https://168886888.xyz',
'https://172.104.33.229:7022',
'https://17yxyy.cc',
'https://18.mamamajd.site',
'https://1run.vip',
'https://1st.760666.xyz',
'https://2.flybar20.cc',
'https://22.lownet.xyz',
'https://2501.xunle.de',
'https://25054128.xyz',
'https://258936.xyz',
'https://261p57.235222.xyz',
'https://4afcn.jp.313132.xyz',
'https://4gsieutoc.tokyo',
'https://5.44.251.106',
'https://54fxp.xyz',
'https://569.2.passwallwall.life',
'https://57dea681-95e1-4f00-8807-302677474a89.38944.xyz',
'https://58rocket.com',
'https://58sd.net',
'https://6.needss.one',
'https://6xp5FU.tosslk.xyz',
'https://7day.wsssapt.org',
'https://88catnet.com',
'https://8rkt.xyz',
'https://91yun.buzz',
'https://a.0123456789.us.kg',
'https://a.112664.xyz',
'https://a.977344.xyz',
'https://a.aik88.top',
'https://a.kpyun.live',
'https://a.opk.icu',
'https://a.yousu.cc',
'https://a02.qytvipaffa01.cc',
'https://a03.qytvipaff.pro',
'https://a1.8jiasu.com',
'https://a1.allbluess.pro',
'https://a123.buzz',
'https://abc.noseisei.com',
'https://abcd168.icu',
'https://abyssvpn.com',
'https://admin.linkerror.cc',
'https://aeda2.asa.lol',
'https://affman.mellanox.fyi',
'https://afun.la',
'https://afun-waf.trafficmanager.net',
'https://aikx.me',
'https://air.aptlive.org',
'https://air.misakano.eu.org',
'https://air.yoyoss.xyz',
'https://air001.dianying.my',
'https://airport.lat',
'https://airport.raloar.top',
'https://apanel.tinnyrick.com',
'https://api.dashsp.top',
'https://api.download.xiaohuojian.store',
'https://api.e986532.top',
'https://api.nfspeed01.com',
'https://api.niuniunet.com',
'https://api.node.wanhai.sbs',
'https://api.vetcross.work',
'https://api.xinghongapi.xyz',
'https://api.xuebifast.com',
'https://api114514.nuwaa.rest',
'https://app.birds.hk',
'https://app.cloudlion.me',
'https://app.cloudog.me',
'https://app.denza.xyz',
'https://app.gomeow.cloud',
'https://app.legeth.cc',
'https://app.vnet.ltd',
'https://arisaka.io',
'https://asa.lol',
'https://askahh.com',
'https://av8dcloud.top',
'https://ayucloud.services',
'https://az.170203.xyz',
'https://az.233235.xyz',
'https://az.757866.xyz',
'https://az2.233235.xyz',
'https://azyun.top',
'https://b.xiaow.cc',
'https://b.yousu.cc',
'https://b0chi.r-yu.me',
'https://b1.mikasass.pro',
'https://b1tf1t.top',
'https://bailian.site',
'https://baimao.us',
'https://baiyangxing.com',
'https://bajie.info',
'https://bajie.pw',
'https://bbs.cloudnetwork.pro',
'https://bbxy.xn--cesw6hd3s99f.com',
'https://bcast.ink',
'https://besnow.me',
'https://bityun.org',
'https://blueoneapp.com',
'https://board.jike99.xyz',
'https://bobapp.nfspeed01.com',
'https://bobapp.xuebifast.com',
'https://bobapp.xuebispeed.com',
'https://bt3.one',
'https://by.yunduanjc.top',
'https://byijsq.com',
'https://c.xunle.de',
'https://c.yousu.cc',
'https://c3.tolinkss.pro',
'https://c6jxw.xffvps.eu.org',
'https://cainiao216.top',
'https://cainiao217.top',
'https://cainiao220.top',
'https://cainiao221.top',
'https://cainiao223.top',
'https://cainiao224.top',
'https://cccccc.iyiyun.xyz',
'https://cd520.xyz',
'https://cdn.ednovas.org',
'https://cdn.yom666.net',
'https://changyouvpn.top',
'https://chiguayun.com',
'https://chiguayun.net',
'https://chiguayun.org',
'https://chuifengji.top',
'https://chy.fit',
'https://client.3i.lol',
'https://cloud.jisuba.live',
'https://cloud.jisuba.me',
'https://cloud.speedypro.xyz',
'https://cloud.speedyweb.xyz',
'https://cloudfox.club',
'https://cn.newbee.cyou',
'https://cn.newbee888.cc',
'https://cocolink.org',
'https://cokecloud.me',
'https://cokecloud.net',
'https://cxk.lol',
'https://d58e3582afa99040e27b92b13c8f2280.boluoidc.com',
'https://daniu.e300daniu.top',
'https://darkforest.cloud',
'https://dash.afun.la',
'https://dash.bigcow.cc',
'https://dash.fscloud.cc',
'https://dash.harry.lv',
'https://dash.legeth.com',
'https://dash.minizz.online',
'https://dash2.moonriver.one',
'https://dash3.moonriver.one',
'https://dash4.moonriver.one',
'https://dash5.moonriver.one',
'https://dashuai.us',
'https://daxun.club',
'https://db.shellnet.net',
'https://db01.in',
'https://dd.moonriver.cfd',
'https://ddddd.site',
'https://dddy.568789.xyz',
'https://ddsfsdfsdf.tiktok.casa',
'https://deepquery.cn',
'https://dingmei2.bajie1.me',
'https://dingyue.xjay.xyz',
'https://dns.mytonxs.uk',
'https://doucat.top',
'https://download.chaincloud.top',
'https://dy.lime5.xyz',
'https://dy.niuniunet.com',
'https://dy.yh13.xyz',
'https://dy.yooyo.top',
'https://dy2.forerunnercn.xxzss.store',
'https://dy3.yunhu1.xyz',
'https://f.wwwq.net',
'https://fast.sudatech.store',
'https://fast.thenight.icu',
'https://fastestcloud.xyz',
'https://FdxjrlMBE8.mofangsub01.lol',
'https://feigou.zhunchuanpb.com',
'https://fengwo.pro',
'https://fil1.cloud.fil.firm.in.31465.cfd',
'https://filashe.org',
'https://fly.6128888.xyz',
'https://flybirdy.xyz',
'https://flybit.vip',
'https://foxtiming.com',
'https://fpacecloud.com',
'https://g871cec.cdn.uunode.com',
'https://gd.kaxinzx.cc',
'https://getcdn.cache.php.wanhai.sbs',
'https://gfw.best',
'https://gg.mqs.xyz',
'https://glados.network',
'https://glados.one',
'https://glados.space',
'https://go.yueyun.de',
'https://gogoyun.org',
'https://gotocdn.tencentagi.com',
'https://gsmoney.uk',
'https://guanwang.me',
'https://guobaotegong.me',
'https://haoba.cloud',
'https://home.wkyuns.xyz',
'https://hongxingdl.com',
'https://hongxingdl.love',
'https://honven20.dgywzc.com',
'https://hoo.caaa.tech',
'https://hssl8088.icu',
'https://huajic.link',
'https://huiguodingyue.yingmaox.cc',
'https://huojian.02000.net',
'https://hx666.02000.net',
'https://hy-2.com',
'https://hy-2.sbs',
'https://ikuuu.me',
'https://ikuuu.pw',
'https://inets.io',
'https://ins.ins66.com',
'https://invite6.cht.taipei',
'https://j8cloud.top',
'https://jgjs02.com',
'https://jiasu.la',
'https://jiasuba.xyz',
'https://jiedian.666811.xyz',
'https://jisovpn.site',
'https://jisu2.02000.net',
'https://jisu3.02000.net',
'https://jisu4.02000.net',
'https://jjz2.31465.cfd',
'https://jkcloud.net',
'https://jk-cloud.net',
'https://jp.krc4.com',
'https://jp.taishan.pro',
'https://jwlingjing.shop',
'https://kaikaixinxin.me',
'https://kaolacloud.site',
'https://kaxin.cc',
'https://kedouair.top',
'https://kjdsyun.com',
'https://klxq.djgskc.top',
'https://ktmcloud.top',
'https://kuailejc.xyz',
'https://kuaiqiangshou.xyz',
'https://kuajing.pro',
'https://kugou.cloud',
'https://kw83v.us.313132.xyz',
'https://kwa.lol',
'https://lanmaoyun.icu',
'https://latiao.club',
'https://latiao.us',
'https://liangyuandian.club',
'https://lianjia.me',
'https://lianjiajichang.com',
'https://lianjiasub.work',
'https://lime1.xyz',
'https://liulangdiqiu.cc',
'https://live.cute-cloud.de',
'https://lksi.xyz',
'https://love.52pokemon.cc',
'https://main.cute-cloud.de',
'https://maoyun3.com',
'https://maple.icu',
'https://marslink.org',
'https://mc.jiedianxielou.workers.dev',
'https://mcecloud.com',
'https://mdss.cloud',
'https://mgnet.vip',
'https://mgxiaowu.net',
'https://mianmd.ninja',
'https://miaona.co',
'https://miaona.org',
'https://miaona.xyz',
'https://miaovpn.org',
'https://mlshu.com',
'https://mly01.miaolianyun.my',
'https://moes.lnaspiring.com',
'https://mogufan.com',
'https://moonriver.one',
'https://mpddt.top',
'https://mvet.info',
'https://mxwljsq.xyz',
'https://my.catfaka.com',
'https://my.emovpns.top',
'https://my.jetfast.dev',
'https://my.legeth.com',
'https://my.netv2.net',
'https://my.pianyi.info',
'https://MyEO9v.absslk.xyz',
'https://naisicloud.xyz',
'https://nanbei.buzz',
'https://nanbei.cloud',
'https://nanmin.xyz',
'https://necloud.win',
'https://needss.link',
'https://neko.services',
'https://neko.yuriuni.com',
'https://netflix-co.vip',
'https://netv2.net',
'https://network2.magic-in-china.com',
'https://newserver.t1i.top',
'https://nexx.us.kg',
'https://ni8.zxm.cc',
'https://niercloud.com',
'https://nmkjvpn.com',
'https://nova.live',
'https://nyapi.chinacmcc.xyz',
'https://o274i.xffvps.eu.org',
'https://ocloudvpn.com',
'https://ofonet.net',
'https://ol.yoyokid.win',
'https://onee.usero.cn',
'https://onefall.top',
'https://online.yocloud.org',
'https://op5.yydsnode.com',
'https://oukasou.xyz',
'https://ov2rayo.top',
'https://page.sulink.one',
'https://panel.darkbaz.org',
'https://panel.fast8888.com',
'https://panel.keleofficial.com',
'https://panel.moon2046.com',
'https://panel.nextnet.one',
'https://panel.nfspeed01.com',
'https://panel.xuebifast.com',
'https://panel2.fast8888.com',
'https://passwall.link',
'https://pavo.eu.org',
'https://pay.666811.xyz',
'https://pay.xinghongpay.top',
'https://pfjc.im',
'https://pkq.xlm.plus',
'https://planb.cat',
'https://plu.socoo-best.xyz',
'https://pmy666.xyz',
'https://po1.6128888.xyz',
'https://po2.6128888.xyz',
'https://po3.6128888.xyz',
'https://poqiang.site',
'https://port.baozipu.cc',
'https://portal.buddhajumpsoverthewall.com',
'https://portal.passgfw.top',
'https://portal.speedyyun.com',
'https://powerwan.net',
'https://px.bt3.one',
'https://px.xinyo.me',
'https://qianggewangluo.com',
'https://qiaoxbbq.com',
'https://qingyunti.cc',
'https://qytvipaffcc04.qytvipaff.pro',
'https://reborn.kaochang.ltd',
'https://reurl.cc',
'https://s.jiasu01.vip',
'https://s1.byte11.com',
'https://s1.equinoxaa.com',
'https://s2.equinoxaa.com',
'https://s3.equinoxaa.com',
'https://sadzxc.xyz',
'https://saiboyun.icu',
'https://saiboyun.link',
'https://saiboyun.org',
'https://sanxijichang.com',
'https://service.mf-api1.site',
'https://service.mofangcloud.shop',
'https://shandiandog.com',
'https://shopvpn.net',
'https://shuimu.site',
'https://sidog.top',
'https://siris.eu.org',
'https://site01.stardad.lol',
'https://skyhomevpn.com',
'https://snangua.com',
'https://sockboom.love',
'https://songguanting.eu.org',
'https://soulvpn.net',
'https://south.shuiyun.sbs',
'https://sp.nfsq.me',
'https://sq9xy6.cpminig.com',
'https://ssr.giize.com',
'https://starlink.to',
'https://store.kakocloud.pro',
'https://sttlink.net',
'https://sub.372372.xyz',
'https://sub.blueoneapp.com',
'https://sub.chbjpw.mobi',
'https://sub.cokecloud.world',
'https://sub.nsxwo.com',
'https://sub.ssrsub.com',
'https://sub.xueyejiasu.com',
'https://sub.yocloud.org',
'https://sub1.pingboy.top',
'https://subd.6668898.xyz',
'https://subscribe2628.lanmaoyun.icu',
'https://sulian.life',
'https://suliannet.cn',
'https://sulink.pro',
'https://suo.yt',
'https://superbiu.com',
'https://supz1.6128888.xyz',
'https://suwayun.com',
'https://syq.tw',
'https://syyn.1.passwallwall.life',
'https://tagss04.pro',
'https://tcity8.top',
'https://terfghtll.dashuai.us',
'https://thecom.today',
'https://tiedan.595418.xyz',
'https://tlnnm.ntgdada.top',
'https://tly.sh',
'https://tsbx.6128888.xyz',
'https://tt.yesiamai.com',
'https://ttmjie.235222.xyz',
'https://tz1314.top',
'https://uat-admin.drt-acs.org',
'https://upm8kfu.nicecloud.win:8443',
'https://us.ajiaxi.cyou',
'https://us1.av8dcloud.top',
'https://user.dafeiji.one',
'https://user.susucloud.net',
'https://user.xinna.co',
'https://usla.icola.top',
'https://uuvpn.cloud',
'https://v.cheerfun.dev',
'https://v.moon2046.com',
'https://v02.520131.best',
'https://v1-4-2.qwunessles.online',
'https://v2.moon2046.com',
'https://v2free.net',
'https://v2lnk.net',
'https://v3ssy.xyz',
'https://vcros.net',
'https://vetcross.work',
'https://vip.baima360.com',
'https://vip.izn.cc',
'https://vip.tinnyrick.com',
'https://vip1.nnn666.icu',
'https://vip1.nnn777.icu',
'https://vip1.nnn888.icu',
'https://vip2.nnn666.icu',
'https://vip2.nnn777.icu',
'https://vip2.nnn888.icu',
'https://vip2.uuu888.icu',
'https://vl.yoyocloud.org',
'https://vol.6128888.xyz',
'https://vpn.28.al',
'https://vpn.bpeaed.com',
'https://vpn.gunyoung.top',
'https://vpn.sudatech.store',
'https://vvcloud.us.kg',
'https://vvs.e54.site',
'https://vyy.idsduf.com',
'https://w02.qytl2web01.cc',
'https://w1.v2free.cc',
'https://w2.ddnsgo.xyz',
'https://wamn.icu',
'https://wanhai.sbs',
'https://waterwheel.buzz',
'https://wayen.eu',
'https://web.nnpy.org',
'https://web.saiboyun.xyz',
'https://web2.52pokemon.cc',
'https://web2.dogssr.sbs',
'https://web3.52pokemon.cc',
'https://wfelby.235222.xyz',
'https://wumaojichang.com',
'https://wuyouyun.sbs',
'https://www.1365365.xyz',
'https://www.1655ss.com',
'https://www.168886888.xyz',
'https://www.1belt1road.vip',
'https://www.258936.xyz',
'https://www.58mdss.com',
'https://www.99catnet.com',
'https://www.9yuan.top',
'https://www.aaaspeed.cc',
'https://www.abcd168.icu',
'https://www.aimacloud.info',
'https://www.airport.lat',
'https://www.aoxiangyun.top',
'https://www.baimao.us',
'https://www.cacapex.com',
'https://www.cantonx.com',
'https://www.chaoyue.shop',
'https://www.chinacmcc.xyz',
'https://www.ckckssl.top',
'https://www.cl001.site',
'https://www.diaomaojichang.top',
'https://www.ducklink.net',
'https://www.duguletian.com',
'https://www.dukadi.one',
'https://www.eyujichang.com',
'https://www.f2ray.com',
'https://www.fawncloud.one',
'https://www.flybar13.cc',
'https://www.flybar4.cc',
'https://www.flymetothemoon.work',
'https://www.fooksun.xyz',
'https://www.forerunnervpn.com',
'https://www.genies.top',
'https://www.gogocloud.cyou',
'https://www.gscloud.icu',
'https://www.gspeed.pro',
'https://www.heima360.in',
'https://www.hj521.top',
'https://www.hj522.top',
'https://www.huaxia.cyou',
'https://www.jichang.pro',
'https://www.jwfree.us',
'https://www.kjdsyun.com',
'https://www.kuaidog006.top',
'https://www.kuaidog010.top',
'https://www.laoniu49.top',
'https://www.littleqqq.co',
'https://www.maimaimai.top',
'https://www.mangshe.org',
'https://www.marslink.cc',
'https://www.mbsurf.xyz',
'https://www.meigui168.net',
'https://www.mgjs.site',
'https://www.mgnet.sbs',
'https://www.mgnet.vip',
'https://www.mickey.business',
'https://www.mojie.me',
'https://www.moonriver.sbs',
'https://www.netv2.net',
'https://www.nmkjvpn.com',
'https://www.okanc.com',
'https://www.okvpn.cc',
'https://www.paopao.dog',
'https://www.proxyvip.xyz',
'https://www.qf1.us',
'https://www.qlgq.top',
'https://www.redleaf.cloud',
'https://www.sadzxc.xyz',
'https://www.skyhomevpn.com',
'https://www.smcow.com',
'https://www.starlink9527.xyz',
'https://www.strongswans.net',
'https://www.taishan.pro',
'https://www.tiedan168.net',
'https://www.tiziwrops.com',
'https://www.v2ny.com',
'https://www.v2ssr.top',
'https://www.vfast.life',
'https://www.vpnjc.com.cn',
'https://www.wanhai.sbs',
'https://www.wkyun1688.com',
'https://www.xbyun.live',
'https://www.xfxssr.com',
'https://www.xiahas.top',
'https://www.xn--qprx60h.site',
'https://www.xn--vl1a701a.xyz',
'https://www.yywhale.com',
'https://www.z1z1.top',
'https://www11.henet.uk',
'https://x.235222.xyz',
'https://x2b.eans.top',
'https://xb.718181.xyz',
'https://xbb.cwhome.top',
'https://xbd.iftballs.com',
'https://xboard.qldev.cc',
'https://xboard.ryuuz.cn',
'https://xc1.shishi1.buzz',
'https://x-cdn-1.235222.xyz',
'https://xianyuwangluo.top',
'https://xingoogle.com',
'https://xjyjc.top',
'https://xmfwww.cc',
'https://xn--4gq1dp1ix68g.xyz',
'https://xn--4gq62f.com',
'https://xn--4gq62f52gdss.com',
'https://xn--4gqp1u.com',
'https://xn--4oq11ryli3rg.com',
'https://xn--6nq44rp7f3wj.com',
'https://xn--9kqx21a0sv.com',
'https://xn--iiq540h.com',
'https://xn--mes91t7ofgnw.com',
'https://xn--wtq35pfyd55o.co',
'https://xqsub.e54.site',
'https://xueyejiasu.com',
'https://xunlian.site',
'https://xx-ai.io',
'https://xxx.xiaoshihoukepangle.sbs',
'https://xyz.noseisei.com',
'https://yang521.org',
'https://yang521.top',
'https://yexiaowork.fmvp.al',
'https://ygl28a.235222.xyz',
'https://yhcvpn.xyz',
'https://yihicloud.top',
'https://ykxqn.com',
'https://yun.iyiyun.xyz',
'https://yunduanjc.top',
'https://yunlu.vip',
'https://yuyan.online',
'https://yV4iXJ.mcsslk.xyz',
'https://ywl.201593.xyz',
'https://z.luxury',
'https://z.shipv.net',
'https://zhenshihui.life',
'https://zhenshihui.shop',
'https://zhenxunkeai.top',
'https://zhu.suyun.bio',
'https://zhuiyun.top',
'https://zhuye2.sulink.one',
'https://zongyunti.com',
'https://zouma.guanhua.xyz',
'https://zqjc.org',
'https://zxc.noseisei.com',
'https://zycloud.online',
'https://zzz.youxuan.wiki',


)
#文件路径
update_path = "./sub/"
#所有的clash订阅链接
end_list_clash = []
#所有的v2ray订阅链接
end_list_v2ray = []
#所有的节点明文信息
end_bas64 = []
#获得格式化后的链接
new_list = []
#永久订阅
e_sub = ['']
#频道
urls =[]
#线程池
threads = []
#机场链接
plane_sub = ['']
#机场试用链接
try_sub = []
#获取频道订阅的个数
sub_n = -25
#试用节点明文
end_try = []

#获取群组聊天中的HTTP链接
def get_channel_http(url):
    headers = {
        'sec-ch-ua': '".Not/A)Brand";v="99", "Google Chrome";v="103", "Chromium";v="103"',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Referer': 'https://t.me/s/oneclickvpnkeys',
        'X-Requested-With': 'XMLHttpRequest',
        'sec-ch-ua-mobile': '?0',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36',
        'sec-ch-ua-platform': '"Windows"',
    }
    response = requests.post(
        url, headers=headers)
    #print(response.text)
    pattren = re.compile(r'"https+:[^\s]*"')
    url_lst = pattren.findall(response.text)
    #print('获取到',len(url_lst),'个网址')
    #print(url_lst)
    return url_lst


#对bs64解密
def jiemi_base64(data):  # 解密base64
    # 对 Base64 编码后的字符串进行解码，得到字节字符串
    decoded_bytes = base64.b64decode(data)
    # 使用 chardet 库自动检测字节字符串的编码格式
    encoding = chardet.detect(decoded_bytes)['encoding']
    # 将字节字符串转换为字符串
    decoded_str = decoded_bytes.decode(encoding)
    return decoded_str

#判读是否为订阅链接
def get_content(url):
    #print('【获取频道',url,'】')
    url_lst = get_channel_http(url)
    #print(url_lst)
    #对链接进行格式化
    for i in url_lst:
        result = i.replace("\\", "").replace('"', "")
        if result not in new_list:
            if "t" not in result[8]:
                if "p" not in result[-2]:
                    new_list.append(result)
    #print(new_list)
    #print("共获得", len(new_list), "条链接")
    #获取单个订阅链接进行判断
    i = 1
    try:
        new_list_down = new_list[sub_n::]
    except:
        new_list_down = new_list[len(new_list) * 2 // 3::]
    #print("共获得", len(new_list_down), "条链接")
    #print('【判断链接是否为订阅链接】')
    for o in new_list_down:
        try:
            res = requests.get(o)
            #判断是否为clash
            try:
                skuid = re.findall('proxies:', res.text)[0]
                if skuid == "proxies:":
                    #print(i, ".这是个clash订阅", o)
                    end_list_clash.append(o)
            except:
                #判断是否为v2
                try:
                    #解密base64
                    peoxy = jiemi_base64(res.text)
                    #print(i, ".这是个v2ray订阅", o)
                    end_list_v2ray.append(o)
                    end_bas64.extend(peoxy.splitlines())
                    
                #均不是则非订阅链接
                except:
                    #print(i, ".非订阅链接")
                    pass
        except:
            #print("第", i, "个链接获取失败跳过！")
            pass
        i += 1
    return end_bas64

#写入文件
def write_document():
    if e_sub == [] or try_sub == []:
        print("订阅为空请检查！")
    else:
        #永久订阅
        random.shuffle(e_sub)
        for e in e_sub:
            try:
                res = requests.get(e)
                proxys=jiemi_base64(res.text)
                end_bas64.extend(proxys.splitlines())
            except:
                print(e,"永久订阅出现错误❌跳过")
        print('永久订阅更新完毕')
        #试用订阅
        random.shuffle(try_sub)
        for t in try_sub:
            try:
                res = requests.get(t)
                proxys=jiemi_base64(res.text)
                end_try.extend(proxys.splitlines())
            except Exception as er:
                print(t,"试用订阅出现错误❌跳过",er)
        print('试用订阅更新完毕',try_sub)
        #永久订阅去重
        end_bas64_A = list(set(end_bas64))
        print("去重完毕！！去除",len(end_bas64) - len(end_bas64_A),"个重复节点")
        #永久订阅去除多余换行符
        bas64 = '\n'.join(end_bas64_A).replace('\n\n', "\n").replace('\n\n', "\n").replace('\n\n', "\n")
        #试用去除多余换行符
        bas64_try = '\n'.join(end_try).replace('\n\n', "\n").replace('\n\n', "\n").replace('\n\n', "\n")
        #获取时间，给文档命名用
        t = time.localtime()
        date = time.strftime('%y%m', t)
        date_day = time.strftime('%y%m%d', t)
        #创建文件路径
        try:
            os.mkdir(f'{update_path}{date}')
        except FileExistsError:
            pass
        txt_dir = update_path + date + '/' + date_day + '.txt'
        #写入时间订阅
        file = open(txt_dir, 'w', encoding='utf-8')
        file.write(bas64)
        file.close()       
        
        #减少获取的个数
        r = 1
        length = len(end_bas64_A)  # 总长
        m = 8  # 切分成多少份
        step = int(length / m) + 1  # 每份的长度
        for i in range(0, length, step):
            print("起",i,"始",i+step)
            zhengli = '\n'.join(end_bas64_A[i: i + step]).replace('\n\n', "\n").replace('\n\n', "\n").replace('\n\n', "\n")
            #将获得的节点变成base64加密，为了长期订阅
            obj = base64.b64encode(zhengli.encode())
            plaintext_result = obj.decode()
            #写入长期订阅
            file_L = open("Long_term_subscription"+str(r), 'w', encoding='utf-8')
            file_L.write(plaintext_result)
            r += 1
        #写入总长期订阅
        obj = base64.b64encode(bas64.encode())
        plaintext_result = obj.decode()
        file_L = open("Long_term_subscription_num", 'w', encoding='utf-8')
        file_L.write(plaintext_result)
        #写入试用订阅
        obj_try = base64.b64encode(bas64_try.encode())
        plaintext_result_try = obj_try.decode()
        file_L_try = open("Long_term_subscription_try", 'w', encoding='utf-8')
        file_L_try.write(plaintext_result_try)
        #写入README
        with open("README.md", 'r', encoding='utf-8') as f:
            lines = f.readlines()
            f.close()
        now_time = datetime.datetime.now()
        TimeDate = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for index in range(len(lines)):
            try:
                if lines[index] == '`https://raw.bgithub.xyz/w1770946466/Auto_proxy/main/Long_term_subscription_num`\n':
                    lines.pop(index+1)
                    lines.insert(index+1, f'`Total number of merge nodes: {length}`\n')
                if lines[index] == '`https://raw.bgithub.xyz/w1770946466/Auto_proxy/main/Long_term_subscription1`\n':
                    lines.pop(index+1)
                    lines.insert(index+1, f'`Total number of merge nodes: {step}`\n')
                if lines[index] == '`https://raw.bgithub.xyz/w1770946466/Auto_proxy/main/Long_term_subscription2`\n': # 目标行内容
                    lines.pop(index+1)
                    lines.insert(index+1, f'`Total number of merge nodes: {step}`\n')
                if lines[index] == '`https://raw.bgithub.xyz/w1770946466/Auto_proxy/main/Long_term_subscription3`\n': # 目标行内容
                    lines.pop(index+1)
                    lines.insert(index+1, f'`Total number of merge nodes: {step}`\n')
                if lines[index] == '`https://raw.bgithub.xyz/w1770946466/Auto_proxy/main/Long_term_subscription4`\n': # 目标行内容
                    lines.pop(index+1)
                    lines.insert(index+1, f'`Total number of merge nodes: {step}`\n')
                if lines[index] == '`https://raw.bgithub.xyz/w1770946466/Auto_proxy/main/Long_term_subscription5`\n': # 目标行内容
                    lines.pop(index+1)
                    lines.insert(index+1, f'`Total number of merge nodes: {step}`\n')
                if lines[index] == '`https://raw.bgithub.xyz/w1770946466/Auto_proxy/main/Long_term_subscription6`\n': # 目标行内容
                    lines.pop(index+1)
                    lines.insert(index+1, f'`Total number of merge nodes: {step}`\n')
                if lines[index] == '`https://raw.bgithub.xyz/w1770946466/Auto_proxy/main/Long_term_subscription7`\n': # 目标行内容
                    lines.pop(index+1)
                    lines.insert(index+1, f'`Total number of merge nodes: {step}`\n')
                if lines[index] == '`https://raw.bgithub.xyz/w1770946466/Auto_proxy/main/Long_term_subscription8`\n': # 目标行内容
                    lines.pop(index+1)
                    lines.insert(index+1, f'`Total number of merge nodes: {length-step*7}`\n')
                if lines[index] == '`https://raw.bgithub.xyz/w1770946466/Auto_proxy/main/Long_term_subscription3.yaml`\n': # 目标行内容
                    lines.pop(index+4)
                    lines.pop(index+4)
                    lines.insert(index+4, f'Updata：`{TimeDate}`\n')
                    lines.insert(index+4, f'### Try the number of high-speed subscriptions: `{len(try_sub)}`\n')
                if lines[index] == '>Trial subscription：\n': # 目标行内容
                    lines.pop(index)
                    lines.pop(index)
                """
                if lines[index] == '## ✨Star count\n': # 目标行内容
                    n = 5
                    for TrySub in try_sub:
                        lines.insert(index-n, f'\n>Trial subscription：\n`{TrySub}`\n')
                        n += 3
                """
            except:
                #print("写入READ出错")
                pass
        #写入试用订阅
        for index in range(len(lines)):
            try:
                if lines[index] == '## ✨Star count\n': # 目标行内容
                    n = 5
                    for TrySub in try_sub:
                        #lines.insert(index+n-1, f'\n>')
                        lines.insert(index-n, f'\n>Trial subscription：\n`{TrySub}`\n')
                        n += 3
            except:
                print("写入试用出错")
        
        with open("README.md", 'w', encoding='utf-8') as f:
            data = ''.join(lines)
            f.write(data)
        print("合并完成✅")
        try:
            numbers =sum(1 for _ in open(txt_dir))
            print("共获取到",numbers,"节点")
        except:
            print("出现错误！")
        
    return

#获取clash订阅
def get_yaml():
    print("开始获取clsah订阅")
    urls = []
    n = 1
    for i in urls:
        response = requests.get(i)
        #print(response.text)
        file_L = open("Long_term_subscription" + str(n) +".yaml", 'w', encoding='utf-8')
        file_L.write(response.text)
        file_L.close()
        n += 1
    print("clash订阅获取完成！")

#获取机场试用订阅
def get_sub_url():
    V2B_REG_REL_URL = '/api/v1/passport/auth/register'
    times = 1
    for current_url in home_urls:
        i = 0
        while i < times:
            header = {
                'Referer': current_url,
                'User-Agent': 'Mozilla/5.0 (iPad; CPU OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1',
                'Content-Type': 'application/x-www-form-urlencoded',
            }
            form_data = {
                'email': ''.join(random.choice(string.ascii_letters+string.digits) for _ in range(12))+'@gmail.com',
                'password': 'autosub_v2b',
                'invite_code': '',
                'email_code': ''
            }
            if current_url == 'https://xn--4gqu8thxjfje.com' or current_url == 'https://seeworld.pro'  or current_url == 'https://www.jwckk.top'or current_url == 'https://vvtestatiantian.top':
                try:
                    fan_res = requests.post(
                        f'{current_url}/api/v1/passport/auth/register', data=form_data, headers=header)
                    auth_data = fan_res.json()["data"]["auth_data"]
                    #print(auth_data)
                    fan_header = {
                        'Origin': current_url,
                        'Authorization': ''.join(auth_data),
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'Connection': 'keep-alive',
                        'User-Agent': 'Mozilla/5.0 (iPad; CPU OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1',
                        'Referer': current_url,
                    }
                    fan_data = {
                        'period': 'onetime_price',
                        'plan_id': '1',
                    }
                    fan_res_n = requests.post(
                        f'{current_url}/api/v1/user/order/save', headers=fan_header, data=fan_data)
                    #print(fan_res_n.json()["data"])
                    fan_data_n = {
                        'trade_no':fan_res_n.json()["data"],
                        #'method': '1',
                    }
                    fan_res_pay = requests.post(
                        f'{current_url}/api/v1/user/order/checkout', data=fan_data_n, headers=fan_header)
                    subscription_url = f'{current_url}/api/v1/client/subscribe?token={fan_res.json()["data"]["token"]}'
                    try_sub.append(subscription_url)
                    e_sub.append(subscription_url)
                    print("add:"+subscription_url)
                except Exception as result:
                    print(result)
                    break
            else:
                try:
                    response = requests.post(
                        current_url+V2B_REG_REL_URL, data=form_data, headers=header)
                    subscription_url = f'{current_url}/api/v1/client/subscribe?token={response.json()["data"]["token"]}'
                    try_sub.append(subscription_url)
                    e_sub.append(subscription_url)
                    print("add:"+subscription_url)
                except Exception as e:
                    print("获取订阅失败",e)
            i += 1

            
  
def get_kkzui():
    # ========== 抓取 kkzui.com 的节点 ==========
    try:
        headers = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36 Edg/105.0.1343.53"}
        res = requests.get("https://kkzui.com/jd?orderby=modified",headers=headers)
        article_url = re.search(r'<h2 class="item-heading"><a href="(https://kkzui.com/(.*?)\.html)"',res.text).groups()[0]
        #print(article_url)
        res = requests.get(article_url,headers=headers)
        sub_url = re.search(r'<p><strong>这是v2订阅地址</strong>：(.*?)</p>',res.text).groups()[0]
        print(sub_url)
        e_sub.append(sub_url)
        print("获取kkzui.com完成！")
    except:
        print("获取kkzui.com失败！")
    try:
        headers = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36 Edg/105.0.1343.53"}
        res = requests.get("https://www.cfmem.com/search/label/free",headers=headers)
        article_url = re.search(r"https?://www\.cfmem\.com/\d{4}/\d{2}/\S+v2rayclash-vpn.html",res.text).group()
        #print(article_url)
        res = requests.get(article_url,headers=headers)
        sub_url = re.search(r'>v2ray订阅链接&#65306;(.*?)</span>',res.text).groups()[0]
        print(sub_url)
        try_sub.append(sub_url)
        e_sub.append(sub_url)
    except Exception as e:
        print(e)
        
    
if __name__ == '__main__':
    print("========== 开始获取机场订阅链接 ==========")
    get_sub_url()
    print("========== 开始获取kkzui.com订阅链接 ==========")
    get_kkzui()
    print("========== 开始获取频道订阅链接 ==========")
    for url in urls:
        #print(url, "开始获取......")
        thread = threading.Thread(target=get_content,args = (url,))
        thread.start()
        threads.append(thread)
        #resp = get_content(get_channel_http(url))
        #print(url, "获取完毕！！")
    #等待线程结束
    for t in tqdm(threads):
        t.join()
    print("========== 准备写入订阅 ==========")
    res = write_document()
    clash_sub = get_yaml()
    print("========== 写入完成任务结束 ==========")
