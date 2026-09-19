"""Them playlist Blender vao khoa 7.

Chay tren VPS:
  docker compose exec -T web python manage.py shell < scripts/seed_blender_course_7.py
"""
from django.db import transaction
from training.models import Course, Chapter, Lesson

COURSE_ID = 7
DURATION = 15
VIDEOS = [
  {
    "index": 1,
    "id": "AiA5HoBVBgM",
    "title": "✅ NÊN HỌC BLENDER KHÔNG | HỌC BLENDER"
  },
  {
    "index": 2,
    "id": "1IG9pk2cyg4",
    "title": "✅ IS BLENDER HARD TO LEARN AND HOW TO LEARN BLENDER EFFECTIVELY | LEARNING BLENDER"
  },
  {
    "index": 3,
    "id": "IsT6IeM_oGk",
    "title": "✅ TỰ HỌC BLENDER CƠ BẢN TỪ CHƯA BIẾT GÌ | HỌC BLENDER"
  },
  {
    "index": 4,
    "id": "uOZuZHL4VyY",
    "title": "✅ HƯỚNG DẪN CÀI ĐẶT BLENDER MỚI NHẤT FULL MIỄN PHÍ | Học Blender"
  },
  {
    "index": 5,
    "id": "c-zIeYu68xs",
    "title": "✅ HOW TO DOWNLOAD OLDER VERSIONS OF BLENDER | LEARN BLENDER"
  },
  {
    "index": 6,
    "id": "ONQlXib_IiE",
    "title": "✅ HOW TO RENDER AND EXPORT IMAGES IN BLENDER QUICKLY | LEARN BLENDER"
  },
  {
    "index": 7,
    "id": "HnQW8Wc9Uc8",
    "title": "✅ CÁCH RENDER ANIMATION, XUẤT VIDEO TRONG BLENDER | HỌC BLENDER"
  },
  {
    "index": 8,
    "id": "UB7qmameL_Q",
    "title": "✅ GET ACQUAINTED WITH THE BLENDER SOFTWARE INTERFACE | LEARN BLENDER"
  },
  {
    "index": 9,
    "id": "6CDOBJspjn8",
    "title": "✅ HOW TO ADD/REMOVE WORKSPACES AND CUSTOMIZE YOUR INTERFACE | LEARN BLENDER"
  },
  {
    "index": 10,
    "id": "r5a3NP0djhQ",
    "title": "✅ CÁC CÔNG CỤ BLENDER | HỌC BLENDER"
  },
  {
    "index": 11,
    "id": "FjN1NTyfoGU",
    "title": "✅ HOW TO ZOOM IN BLENDER | LEARN BLENDER"
  },
  {
    "index": 12,
    "id": "sPixx4r6lpA",
    "title": "✅ NUMPAD TRONG BLENDER | HỌC BLENDER"
  },
  {
    "index": 13,
    "id": "qVGalaHhJDM",
    "title": "✅ VIETNAMESE INTERFACE IN BLENDER, HOW TO CHANGE LANGUAGES IN BLENDER | LEARN BLENDER"
  },
  {
    "index": 14,
    "id": "byZO4O7bQ6I",
    "title": "✅ CÁCH DI CHUYỂN VẬT THỂ TRONG BLENDER | HỌC BLENDER"
  },
  {
    "index": 15,
    "id": "B5cVqjEBTWo",
    "title": "✅ NHÂN ĐÔI TRONG BLENDER | HỌC BLENDER"
  },
  {
    "index": 16,
    "id": "FIK1edwK2fU",
    "title": "✅ HOW TO DUPLICATE OBJECTS FOLLOWING Distorted and Undistorted Paths | LEARN BLENDER"
  },
  {
    "index": 17,
    "id": "FTFUY4gdD0A",
    "title": "✅ HOW TO DUPLICATE ANIMATED OBJECTS IN BLENDER | LEARN BLENDER"
  },
  {
    "index": 18,
    "id": "ZoMyvc56JIw",
    "title": "✅ CÁCH ẨN HIỆN VẬT THỂ ĐANG CHỌN | HỌC BLENDER"
  },
  {
    "index": 19,
    "id": "PzyBB-AvNEw",
    "title": "✅ FREE BLENDER ASSET LIBRARIES | LEARN BLENDER"
  },
  {
    "index": 20,
    "id": "Sw0L73M7KMw",
    "title": "✅ HOW TO OPEN SKETCHUP FILE INTO BLENDER | LEARN BLENDER"
  },
  {
    "index": 21,
    "id": "zpI2UFnj4Tk",
    "title": "✅ THƯ VIỆN BLENDER KIT CÀI VÀO MIỄN PHÍ | HỌC BLENDER"
  },
  {
    "index": 22,
    "id": "gEtMROuy83s",
    "title": "✅ FREE 3D MODEL LIBRARIES FOR BLENDER | LEARN BLENDER"
  },
  {
    "index": 23,
    "id": "I1FOc6gkMMk",
    "title": "✅ HOW TO USE VDB ANIMATION LIBRARIES: CLOUD, SMOKE, FIRE, WATER, DUST, EXPLOSION, STORM | LEARN B..."
  },
  {
    "index": 24,
    "id": "Bs3SRL8mFbw",
    "title": "✅ BẮT ĐIỂM TRONG BLENDER, ALIGN TRONG BLENDER | HỌC BLENDER"
  },
  {
    "index": 25,
    "id": "04Uw1jSAS6Q",
    "title": "✅ GROUP IN BLENDER | LEARN BLENDER"
  },
  {
    "index": 26,
    "id": "kZP14mAQQac",
    "title": "✅ UNGROUP IN BLENDER | LEARN BLENDER"
  },
  {
    "index": 27,
    "id": "V_HZjcVc-AQ",
    "title": "✅ BLENDER SHORTCUTS | LEARN BLENDER"
  },
  {
    "index": 28,
    "id": "Efm4OczjFgU",
    "title": "✅ HOW TO FOCUS ON THE BLENDER OBJECT | LEARN BLENDER"
  },
  {
    "index": 29,
    "id": "EJntO32Q8Js",
    "title": "✅ HOW TO SELECT EDGES, FACES, AND VERTICES IN BLENDER | BLENDER TUTORIAL"
  },
  {
    "index": 30,
    "id": "sxqYzK0sbqI",
    "title": "✅ ADDING EDGES IN BLENDER | LEARN BLENDER"
  },
  {
    "index": 31,
    "id": "LW4m7xKkKB0",
    "title": "✅ HOW TO SEPARATE OBJECTS AND CUT MESHES IN BLENDER | BLENDER TUTORIAL"
  },
  {
    "index": 32,
    "id": "6rcCRT1MeRo",
    "title": "✅ HOW TO CUT AND SEPARATE OBJECTS IN BLENDER | LEARN BLENDER"
  },
  {
    "index": 33,
    "id": "e8eBVKAMHT8",
    "title": "✅ HOW TO INCREASE MESH DENSITY IN SCULPTING | LEARN BLENDER"
  },
  {
    "index": 34,
    "id": "K6yTxfKmQnE",
    "title": "✅ LOCK BLENDER OBJECTS | LEARN BLENDER"
  },
  {
    "index": 35,
    "id": "8-20vX4LHS4",
    "title": "✅ CÁCH LẤP MẶT HỞ, CAP HOLES TRONG BLENDER | HỌC BLENDER"
  },
  {
    "index": 36,
    "id": "6gttvD4VixI",
    "title": "✅ HOW TO INCREASE MESH DENSITY IN BLENDER EDIT MODE | LEARN BLENDER"
  },
  {
    "index": 37,
    "id": "JP_bvr8ruBc",
    "title": "✅ MERGE IN BLENDER | LEARN BLENDER"
  },
  {
    "index": 38,
    "id": "lqpvBTZUvtU",
    "title": "✅ HOW TO CONNECT 2 VERTICES IN BLENDER | BLENDER TUTORIAL"
  },
  {
    "index": 39,
    "id": "B0SDna99Z70",
    "title": "✅ CÁCH THÊM ĐIỂM TRONG BLENDER | HỌC BLENDER"
  },
  {
    "index": 40,
    "id": "g_FTeyOdUmg",
    "title": "✅ CÁCH ĐỤC LỖ BẰNG BEVEL VÀ BOOLEAN TRONG BLENDER | HỌC BLENDER"
  },
  {
    "index": 41,
    "id": "T9nbeR9ToGg",
    "title": "✅ SMOOTHING OBJECTS, SMOOTH SHADE BLENDER | LEARN BLENDER"
  },
  {
    "index": 42,
    "id": "OhhKrmuDPJE",
    "title": "✅ TRANSPARENCY IN BLENDER, MODELING WITH TRANSPARENCY | LEARN BLENDER"
  },
  {
    "index": 43,
    "id": "cfv5oAOxcwc",
    "title": "✅ HOW TO REDUCE MESH IN BLENDER | LEARN BLENDER"
  },
  {
    "index": 44,
    "id": "2Wu3Jn2Ykso",
    "title": "✅ HOW TO WORK WITH LIVE LINK/LIVESYNC WORKFLOW BETWEEN BLENDER AND D5 RENDER | LEARN BLENDER"
  },
  {
    "index": 45,
    "id": "6GC2rDyStYE",
    "title": "✅ Free Blender Material Library | LEARN BLENDER"
  },
  {
    "index": 46,
    "id": "H6JvI4JgXwA",
    "title": "✅ HOW TO APPLY MATERIALS IN BLENDER, HOW TO APPLY MULTIPLE MATERIALS TO ONE OBJECT | LEARN BLENDER"
  },
  {
    "index": 47,
    "id": "Js6jj3sFTow",
    "title": "✅ CÁCH ĐẶT, CÁCH CHỈNH CAMERA TRONG BLENDER | HỌC BLENDER"
  },
  {
    "index": 48,
    "id": "rRpnb38YquQ",
    "title": "✅ ÁNH SÁNG TRONG BLENDER | HỌC BLENDER"
  },
  {
    "index": 49,
    "id": "HnOgVWMJFK4",
    "title": "✅ HOW TO SET UP ENVIRONMENT LIGHTING | LEARNING BLENDER"
  },
  {
    "index": 50,
    "id": "TBcZCHq9xUc",
    "title": "✅ HOW TO RENDER FASTER IN BLENDER, TIPS TO SPEED UP CYCLES RENDERING | LEARN BLENDER"
  },
  {
    "index": 51,
    "id": "YsGC6jf7XLo",
    "title": "✅ HOW TO RENDER A SMALL AREA, RENDER REGION | LEARN BLENDER"
  },
  {
    "index": 52,
    "id": "wQIIYm-JUMc",
    "title": "✅ CÁCH RENDER RA NỀN SAU BACKGROUND | HỌC BLENDER"
  },
  {
    "index": 53,
    "id": "GkBu-6OTFf8",
    "title": "✅ BLENDER BRUSH SHORTCUTS: RESIZE, STRENGTH, AND ROTATE | LEARN BLENDER"
  },
  {
    "index": 54,
    "id": "b4XRNKuFUgE",
    "title": "✅ TRANSPARENCY IN BLENDER, GLASS MATERIALS, HOW TO ADJUST OBJECT TRANSPARENCY | LEARN BLENDER"
  },
  {
    "index": 55,
    "id": "a71VLQzHdrg",
    "title": "✅ HOW TO ADD BACKGROUND IMAGES TO THE BLENDER CAMERA | LEARN BLENDER"
  },
  {
    "index": 56,
    "id": "dJajl2DgqBA",
    "title": "✅ CÁCH CHÈN ẢNH VÀO BLENDER | HỌC BLENDER"
  },
  {
    "index": 57,
    "id": "Bulcb3kBdLE",
    "title": "✅ MATERIAL TRONG BLENDER | HỌC BLENDER"
  },
  {
    "index": 58,
    "id": "BJhcAB5gWNU",
    "title": "✅ SHADING IN BLENDER | LEARN BLENDER"
  },
  {
    "index": 59,
    "id": "SmbwZsOulAE",
    "title": "✅ HOW TO CREATE WATER IN BLENDER | LEARN BLENDER"
  },
  {
    "index": 60,
    "id": "pTyWcqimyHQ",
    "title": "✅ GLASS MATERIALS IN BLENDER | LEARN BLENDER"
  },
  {
    "index": 61,
    "id": "Ao7aJszBfgo",
    "title": "✅ CÁCH CHỌN VẬT LIỆU NHANH | HỌC BLENDER"
  },
  {
    "index": 62,
    "id": "o0R3usBAO7A",
    "title": "✅ HOW TO EXPORT BLENDER ANIMATIONS TO D5 RENDER | LEARN BLENDER"
  },
  {
    "index": 63,
    "id": "75vvGc05rfY",
    "title": "✅ CÁCH CHUYỂN ẢNH THƯỜNG THÀNH 3D BẰNG MONTERMASK, BLENDER, PHOTOSHOP, FIREFLY | HỌC BLENDER"
  },
  {
    "index": 64,
    "id": "xsgRBjXP1Gw",
    "title": "✅ HOW TO TURN PHOTOS INTO MOVING VIDEOS | LEARN BLENDER"
  },
  {
    "index": 65,
    "id": "LezM2Ebydzw",
    "title": "✅ HOW TO TOGGLE GRID IN BLENDER | LEARN BLENDER"
  },
  {
    "index": 66,
    "id": "mrT2G6hoHvc",
    "title": "✅ CÁCH RENDER CROP MỘT VÙNG NHỎ TRONG BLENDER | HỌC BLENDER"
  },
  {
    "index": 67,
    "id": "fiXfWOtbunM",
    "title": "✅ HOW TO CHANGE UNITS IN BLENDER | LEARN BLENDER"
  },
  {
    "index": 68,
    "id": "vMEhLqnZ1ZU",
    "title": "✅ HOW TO RESET BLENDER INTERFACE | LEARN BLENDER"
  },
  {
    "index": 69,
    "id": "7BB7IlOpjAc",
    "title": "✅ MEASURING IN BLENDER, MEASURING DIMENSIONS IN BLENDER | LEARN BLENDER"
  },
  {
    "index": 70,
    "id": "aJkl-GW4UyU",
    "title": "✅ WHY I DON'T USE THE LATEST SOFTWARE VERSIONS FOR WORK | LEARNING BLENDER"
  },
  {
    "index": 71,
    "id": "zkpFzc8GRDM",
    "title": "✅ CÁCH RENDER BẰNG EEVEE (RENDER TỰ CHỈNH THEO Ý MÌNH) | HỌC BLENDER"
  },
  {
    "index": 72,
    "id": "8nrxBKCoT3I",
    "title": "✅ HOW TO CREATE CAMERA TRACKING AND ADD 3D TO VIDEO | LEARN BLENDER"
  },
  {
    "index": 73,
    "id": "D537L_attG0",
    "title": "✅ HOW TO REDUCE LAG AT WORK | LEARN BLENDER"
  },
  {
    "index": 74,
    "id": "EKD6qWjrzTA",
    "title": "✅ WHAT ARE ADD-ONS? 20 COMMONLY USED BLENDER ADD-ONS | LEARNING BLENDER"
  },
  {
    "index": 75,
    "id": "e_TcymHV0Yw",
    "title": "✅ HOW TO CONVERT NORMAL PHOTOS INTO 3D USING AI, THE BEST AI EVER | LEARN BLENDER"
  },
  {
    "index": 76,
    "id": "72pT9ukg0wM",
    "title": "✅ HOW TO USE AI FOR MODELING IN BLENDER | LEARN BLENDER"
  },
  {
    "index": 77,
    "id": "KnDlyeVdXGk",
    "title": "✅ HOW TO ANIMATE OCEAN WATER, DOWNLOAD ASSET FILES | LEARN BLENDER"
  },
  {
    "index": 78,
    "id": "kxxHfboasiI",
    "title": "✅ HOW TO TURN MESHES INTO WIREFRAMES | LEARN BLENDER"
  },
  {
    "index": 79,
    "id": "dNwGIcAM_rE",
    "title": "✅ HOW TO ADD MUSIC TO BLENDER SOFTWARE | LEARN BLENDER"
  },
  {
    "index": 80,
    "id": "x8MnOZkHFtM",
    "title": "✅ BALL BLANKET PART 0: SETUP AND ADD MUSIC | LEARN BLENDER"
  },
  {
    "index": 81,
    "id": "27pFKYc1AqY",
    "title": "✅ ROLLER BALL PART 2: MUSICAL NOTE NUMBER 1 AND CREATING A GLOW | LEARN BLENDER"
  },
  {
    "index": 82,
    "id": "LzOLfNUDJNY",
    "title": "✅ ROLLER BALL PART 3: MUSICAL NOTE 2 JOINING AND STANDARD TEST PARAMETERS | LEARN BLENDER"
  },
  {
    "index": 83,
    "id": "6eHxCI2iZ5o",
    "title": "✅ ROLLER BALL PART 4: CREATING CURVES | LEARNING BLENDER"
  },
  {
    "index": 84,
    "id": "08EbL4Q_IrU",
    "title": "✅ ROLLER BLENDER PART 7: CREATING STAR AND END-END RENDER JOINTS | LEARN BLENDER"
  },
  {
    "index": 85,
    "id": "9apv02F7J90",
    "title": "✅ HOW TO USE AI TO CREATE ANIMATION WITH CASCADUER SOFTWARE | LEARN BLENDER"
  },
  {
    "index": 86,
    "id": "ok_WDGml1Lk",
    "title": "✅ HOW TO INSTALL CASCADEUR | LEARN BLENDER"
  },
  {
    "index": 87,
    "id": "xS03JOnXTGM",
    "title": "✅ HOW TO CREATE FIRE WITH EMBERGEN | LEARN BLENDER"
  },
  {
    "index": 88,
    "id": "0nEkkAeCyZ4",
    "title": "✅ ROLLING BALL PART 1: BUILDING THE SCENE | LEARNING BLENDER"
  },
  {
    "index": 89,
    "id": "fdu-F6YosE8",
    "title": "✅ ROLLING BALL PART 5: CAMERA ANIMATION SETUP | LEARNING BLENDER"
  },
  {
    "index": 90,
    "id": "64VYtw7Szz0",
    "title": "✅ ROLLING BALL PART 6: CREATING A SEAMLESS LOOP | LEARN BLENDER"
  },
  {
    "index": 91,
    "id": "S3FvsGRguPc",
    "title": "✅ ROLLING BALL PART 8: BUILDING SLIDER RAILS AND USING AI CHARACTER MODELS | LEARNING BLENDER"
  },
  {
    "index": 92,
    "id": "63az75CSkqM",
    "title": "✅ HOW TO ANIMATE A RIG | BLENDER TUTORIAL"
  },
  {
    "index": 93,
    "id": "6NefyacJ1Ts",
    "title": "✅ HOW TO RENDER ANIMATED FILMS | LEARN BLENDER"
  },
  {
    "index": 94,
    "id": "6VqrMnkD3sc",
    "title": "✅ HOW TO CREATE A RIG | LEARNING BLENDER"
  },
  {
    "index": 95,
    "id": "81D_-giTpnI",
    "title": "✅ HOW TO MAKE A CHARACTER FOLLOW A PATH | LEARN BLENDER"
  },
  {
    "index": 96,
    "id": "8QPEOeyRHO8",
    "title": "✅ HOW TO COMPOSITE 3D INTO PHOTOS VIRTUAL STAGING | LEARN BLENDER"
  },
  {
    "index": 97,
    "id": "94zZW8Dui94",
    "title": "✅ HOW TO RIG A MODEL | LEARN BLENDER"
  },
  {
    "index": 98,
    "id": "BZ14sHZjTRY",
    "title": "✅ HOW TO CREATE A RIG FOR A SKIN MODIFIER MESH | LEARN BLENDER"
  },
  {
    "index": 99,
    "id": "BZIQJt52ShA",
    "title": "✅ HOW TO CONVERT ANIMATIONS INTO PARAMETERS | LEARN BLENDER"
  },
  {
    "index": 100,
    "id": "CDkwHHRLKpI",
    "title": "✅ BEST ANIMATION ADD-ONS | LEARNING BLENDER"
  },
  {
    "index": 101,
    "id": "DP6urbmQl2s",
    "title": "✅ HOW TO CREATE A BASIC RIG | BLENDER TUTORIAL"
  },
  {
    "index": 102,
    "id": "E72cQLOxPQs",
    "title": "✅ HOW TO RENDER WITH BACKGROUND | LEARN BLENDER"
  },
  {
    "index": 103,
    "id": "FrXr_0Z01WA",
    "title": "✅ HOW TO CREATE MOTION ALONG A PATH | BLENDER TUTORIAL"
  },
  {
    "index": 104,
    "id": "LTdQX-XXXM8",
    "title": "✅ HOW TO INSTALL THE RIGGING LIBRARY | LEARN BLENDER"
  },
  {
    "index": 105,
    "id": "MEgHOalRDbQ",
    "title": "✅ HOW TO CREATE BLENDER MATERIALS | LEARN BLENDER"
  },
  {
    "index": 106,
    "id": "O-mUADZTc_8",
    "title": "✅ HOW TO CREATE MOTION CONTROLS | LEARN BLENDER"
  },
  {
    "index": 107,
    "id": "VINnjKapKHs",
    "title": "✅ HOW TO SAVE AND RESET BONE POSITIONS | LEARN BLENDER"
  },
  {
    "index": 108,
    "id": "WWA9_H8fJzM",
    "title": "✅ HOW TO SET UP BONES FOR BETTER VISIBILITY | LEARNING BLENDER"
  },
  {
    "index": 109,
    "id": "_jPKIZEuGNA",
    "title": "✅ HOW TO RENDER CAMERA BACKGROUND | LEARN BLENDER"
  },
  {
    "index": 110,
    "id": "fWByAfpVs-8",
    "title": "✅ HOW TO UV UNWRAP FOR TEXTURING | BLENDER TUTORIAL"
  },
  {
    "index": 111,
    "id": "geiX6qO_uEo",
    "title": "✅ CREATE ANIMATION VIDEOS WITH THE BEST CURRENT AI ON PC FOR FREE | LEARN BLENDER"
  },
  {
    "index": 112,
    "id": "iVSYjeJCo0s",
    "title": "✅ CÁCH XOAY TEXTURE KHI VẼ | HỌC BLENDER"
  },
  {
    "index": 113,
    "id": "lCEe4Z6u2V8",
    "title": "✅ HOW TO PAINT TEXTURES IN BLENDER | LEARN BLENDER"
  },
  {
    "index": 114,
    "id": "sERlPxnDyA4",
    "title": "✅ HOW TO CREATE A WALK CYCLE ANIMATION | LEARN BLENDER"
  },
  {
    "index": 115,
    "id": "u0-8JtrPKq8",
    "title": "✅ HOW TO SET UP IK RIGGING | LEARNING BLENDER"
  },
  {
    "index": 116,
    "id": "u8XgdsXwyXA",
    "title": "✅ HOW TO CREATE ANIMATIONS USING ADD-ONS | LEARNING BLENDER"
  },
  {
    "index": 117,
    "id": "ug32b8qs3Xg",
    "title": "✅ TARGET-FOLLOWING EYE MOVEMENT | LEARN BLENDER"
  },
  {
    "index": 118,
    "id": "vNOT5JKkOII",
    "title": "✅ HOW TO CREATE ANIMATIONS WITH ADD-ONS | LEARNING BLENDER"
  },
  {
    "index": 119,
    "id": "vQDmEpH41Zc",
    "title": "✅ HOW TO CREATE BASIC ANIMATION | LEARN BLENDER"
  },
  {
    "index": 120,
    "id": "yJu8tRkmn-I",
    "title": "✅ HOW TO LOOP ANIMATIONS | LEARN BLENDER"
  },
  {
    "index": 121,
    "id": "yk4E_Rvm2Mo",
    "title": "✅ HOW TO RESET ANIMATION KEYS | LEARN BLENDER"
  },
  {
    "index": 122,
    "id": "1QuVe2KeEDg",
    "title": "✅ HOW TO INSTALL EMBERGEN VFX SOFTWARE | LEARN BLENDER"
  },
  {
    "index": 123,
    "id": "2wN0SzhvzH8",
    "title": "✅ HOW TO MODEL USING LINES | LEARN BLENDER"
  },
  {
    "index": 124,
    "id": "64VYtw7Szz0",
    "title": "✅ ROLLING BALL PART 6: CREATING A SEAMLESS LOOP | LEARN BLENDER"
  },
  {
    "index": 125,
    "id": "9apv02F7J90",
    "title": "✅ HOW TO USE AI TO CREATE ANIMATION WITH CASCADUER SOFTWARE | LEARN BLENDER"
  },
  {
    "index": 126,
    "id": "HGr-QQ2scfE",
    "title": "✅ HOW TO MODEL WITH GEOMETRY NODES | LEARN BLENDER"
  },
  {
    "index": 127,
    "id": "J0enPZXARtE",
    "title": "✅ HOW TO SCULPT IN BLENDER | LEARN BLENDER"
  },
  {
    "index": 128,
    "id": "KDdtndzjizc",
    "title": "✅ CREATE 3D CHARACTERS WITH AI FROM MULTIPLE ANGLES | LEARN BLENDER"
  },
  {
    "index": 129,
    "id": "OHm-ggROpAw",
    "title": "✅ WAYS TO MODEL IN BLENDER | LEARN BLENDER"
  },
  {
    "index": 130,
    "id": "QctntSvNGLQ",
    "title": "✅ HOW TO FILL FACES IN BLENDER | LEARN BLENDER"
  },
  {
    "index": 131,
    "id": "S3FvsGRguPc",
    "title": "✅ ROLLING BALL PART 8: BUILDING SLIDER RAILS AND USING AI CHARACTER MODELS | LEARNING BLENDER"
  },
  {
    "index": 132,
    "id": "XSd6sqZE_j0",
    "title": "✅ SCULPTING SHORTCUTS | BLENDER TUTORIAL"
  },
  {
    "index": 133,
    "id": "YZrdw5Wv56M",
    "title": "✅ HOW TO RENDER CYCLES FASTER | LEARN BLENDER"
  },
  {
    "index": 134,
    "id": "ZgzXHX12D9A",
    "title": "✅ HOW TO MODEL WITH SKIN MODIFY | BLENDER TUTORIAL"
  },
  {
    "index": 135,
    "id": "ab_bDGvbvFA",
    "title": "✅ HOW TO ADJUST MATERIAL COLOR AND LIGHTING | LEARN BLENDER"
  },
  {
    "index": 136,
    "id": "aflxbXeC-Dc",
    "title": "✅ HOW TO MODEL A VASE | LEARN BLENDER"
  },
  {
    "index": 137,
    "id": "dNwGIcAM_rE",
    "title": "✅ HOW TO ADD MUSIC TO BLENDER SOFTWARE | LEARN BLENDER"
  },
  {
    "index": 138,
    "id": "fZKfabLqhMc",
    "title": "✅ HOW TO COLOR IN BLENDER | LEARN BLENDER"
  },
  {
    "index": 139,
    "id": "fzqh0uZv6Rc",
    "title": "✅ HOW TO MODEL WITH CURVES | LEARNING BLENDER"
  },
  {
    "index": 140,
    "id": "iUOWCgQotbk",
    "title": "✅ HOW TO CREATE 3D CHARACTERS WITH AI | LEARN BLENDER"
  },
  {
    "index": 141,
    "id": "jwb5vTgD5Lg",
    "title": "✅ BLENDER MODELING METHODS | LEARN BLENDER"
  },
  {
    "index": 142,
    "id": "t1DIlkZVjJ4",
    "title": "✅ HOW TO MODEL AN OBJECT ALONG A PATH | BLENDER TUTORIAL"
  },
  {
    "index": 143,
    "id": "tqFX6PsU6ng",
    "title": "✅ HOW TO MODEL USING SUBDIVISION AND SMOOTHING IN BLENDER | LEARN BLENDER"
  },
  {
    "index": 144,
    "id": "wsEVzHkDFXs",
    "title": "✅ HOW TO MODEL WITH PROPORTIONAL EDITING | LEARN BLENDER"
  },
  {
    "index": 145,
    "id": "xS03JOnXTGM",
    "title": "✅ HOW TO CREATE FIRE WITH EMBERGEN | LEARN BLENDER"
  },
  {
    "index": 146,
    "id": "zG6f2Ix8b30",
    "title": "✅ QUICK SELECTION TIPS FOR MODELING | LEARN BLENDER"
  },
  {
    "index": 147,
    "id": "5HGLto0t2j8",
    "title": "✅ HOW TO IMPORT 3DS MAX FILES INTO BLENDER | LEARN BLENDER"
  },
  {
    "index": 148,
    "id": "72pT9ukg0wM",
    "title": "✅ HOW TO USE AI FOR MODELING IN BLENDER | LEARN BLENDER"
  },
  {
    "index": 149,
    "id": "KnDlyeVdXGk",
    "title": "✅ HOW TO ANIMATE OCEAN WATER, DOWNLOAD ASSET FILES | LEARN BLENDER"
  },
  {
    "index": 150,
    "id": "ghkiHHUkEKQ",
    "title": "✅ HOW TO QUICKLY CREATE MOUNTAINS IN BLENDER | LEARN BLENDER"
  },
  {
    "index": 151,
    "id": "kxxHfboasiI",
    "title": "✅ HOW TO TURN MESHES INTO WIREFRAMES | LEARN BLENDER"
  },
  {
    "index": 152,
    "id": "zp_P0I2LtBs",
    "title": "✅ HOW TO SNAP OBJECTS QUICKLY, QUICK SNAPPING ADDON TOOLKIT | LEARNING BLENDER"
  },
  {
    "index": 153,
    "id": "8rtLJihKP2I",
    "title": "✅ HOW TO QUICKLY SET UP CAMERAS WITH ADD-ONS | LEARN BLENDER"
  },
  {
    "index": 154,
    "id": "3sbJqDs1SxY",
    "title": "✅ HOW TO FILL FACES IN BLENDER | LEARN BLENDER"
  }
]

CHAPTERS = [
    ('Cơ bản', 1, 30),
    ('Nâng cao', 31, 90),
    ('Chuyên nghiệp', 91, 154),
]


def watch_url(video_id):
    return f'https://www.youtube.com/watch?v={video_id}'


course = Course.objects.filter(id=COURSE_ID).first()
if course is None:
    raise SystemExit('Khong tim thay khoa hoc id=7')

print('COURSE', course.pk, course.title)

by_index = {item['index']: item for item in VIDEOS}
created_chapters = 0
created_lessons = 0
skipped_lessons = 0

with transaction.atomic():
    max_chapter_order = course.chapters.order_by('-order').values_list('order', flat=True).first() or 0

    for title, start, end in CHAPTERS:
        chapter = course.chapters.filter(title=title).first()
        if chapter is None:
            max_chapter_order += 1
            chapter = Chapter.objects.create(course=course, title=title, order=max_chapter_order)
            created_chapters += 1
            print('CHAPTER +', chapter.order, chapter.title)
        else:
            print('CHAPTER =', chapter.order, chapter.title)

        max_lesson_order = chapter.lessons.order_by('-order').values_list('order', flat=True).first() or 0
        for idx in range(start, end + 1):
            item = by_index.get(idx)
            if not item:
                print('MISSING index', idx)
                continue
            url = watch_url(item['id'])
            lesson_title = (item['title'] or f'Bai {idx}')[:255]
            if chapter.lessons.filter(order=idx - start + 1, video_url=url).exists():
                skipped_lessons += 1
                continue
            max_lesson_order += 1
            Lesson.objects.create(
                chapter=chapter,
                title=lesson_title,
                lesson_type='video',
                video_url=url,
                order=max_lesson_order,
                duration_estimate=DURATION,
            )
            created_lessons += 1

print('DONE chapters_new', created_chapters, 'lessons_new', created_lessons, 'skipped', skipped_lessons)
print('TOTAL lessons', Lesson.objects.filter(chapter__course=course).count())
