cmake_minimum_required(VERSION 3.15)
project(PocketReticulum LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(RNS_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(RNS_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(RNS_BUILD_INTEROP OFF CACHE BOOL "" FORCE)
set(RNS_USE_PROVISIONING OFF CACHE BOOL "" FORCE)
set(RNS_USE_FS OFF CACHE BOOL "" FORCE)
set(RNS_PERSIST_PATHS OFF CACHE BOOL "" FORCE)
set(RNS_PERSIST_KNOWN_DESTINATIONS OFF CACHE BOOL "" FORCE)
set(RNS_PERSIST_HASHLIST OFF CACHE BOOL "" FORCE)
find_package(Python3 COMPONENTS Interpreter REQUIRED)
execute_process(COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/prepare.py tree
  ${RNS_SOURCE} ${CMAKE_CURRENT_BINARY_DIR}/rns-source RESULT_VARIABLE tree_status)
if(NOT tree_status EQUAL 0)
  message(FATAL_ERROR "Pinned native source preparation failed")
endif()
set(RNS_SOURCE ${CMAKE_CURRENT_BINARY_DIR}/rns-source)
add_subdirectory(${RNS_SOURCE} rns)

find_package(Python3 COMPONENTS Interpreter REQUIRED)
find_package(BZip2 REQUIRED)
execute_process(COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/prepare.py resource
  ${RNS_SOURCE}/src/microReticulum/Resource.cpp ${CMAKE_CURRENT_BINARY_DIR}/PocketResource.cpp
  RESULT_VARIABLE patch_status)
if(NOT patch_status EQUAL 0)
  message(FATAL_ERROR "Pinned native resource preparation failed")
endif()
execute_process(COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/prepare.py packet
  ${RNS_SOURCE}/src/microReticulum/Packet.cpp ${CMAKE_CURRENT_BINARY_DIR}/PocketPacket.cpp RESULT_VARIABLE packet_status)
if(NOT packet_status EQUAL 0)
  message(FATAL_ERROR "Pinned packet proof preparation failed")
endif()
execute_process(COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/prepare.py link
  ${RNS_SOURCE}/src/microReticulum/Link.cpp ${CMAKE_CURRENT_BINARY_DIR}/PocketLink.cpp RESULT_VARIABLE link_status)
if(NOT link_status EQUAL 0)
  message(FATAL_ERROR "Pinned link receipt preparation failed")
endif()
execute_process(COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/prepare.py identity
  ${RNS_SOURCE}/src/microReticulum/Identity.cpp ${CMAKE_CURRENT_BINARY_DIR}/PocketIdentity.cpp RESULT_VARIABLE identity_status)
if(NOT identity_status EQUAL 0)
  message(FATAL_ERROR "Pinned announce-cache preparation failed")
endif()
get_target_property(rns_sources microReticulum SOURCES)
list(FILTER rns_sources EXCLUDE REGEX "/(Resource|Packet|Link|Identity)[.]cpp$")
set_property(TARGET microReticulum PROPERTY SOURCES ${rns_sources} ${CMAKE_CURRENT_BINARY_DIR}/PocketResource.cpp ${CMAKE_CURRENT_BINARY_DIR}/PocketPacket.cpp ${CMAKE_CURRENT_BINARY_DIR}/PocketLink.cpp ${CMAKE_CURRENT_BINARY_DIR}/PocketIdentity.cpp)
target_include_directories(microReticulum PRIVATE ${RNS_SOURCE}/src/microReticulum)
target_link_libraries(microReticulum PUBLIC BZip2::BZip2)

execute_process(COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/prepare.py msgpack
  ${RNS_MSGPACK_SOURCE_DIR} ${CMAKE_CURRENT_BINARY_DIR}/msgpack RESULT_VARIABLE msgpack_status)
if(NOT msgpack_status EQUAL 0)
  message(FATAL_ERROR "Pinned microLXMF MessagePack preparation failed")
endif()
target_include_directories(microReticulum BEFORE PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/msgpack)
execute_process(COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/prepare.py lxmf
  ${LXMF_SOURCE}/src/LXMF/LXMRouter.cpp ${CMAKE_CURRENT_BINARY_DIR}/PocketLXMRouter.cpp RESULT_VARIABLE lxmf_status)
if(NOT lxmf_status EQUAL 0)
  message(FATAL_ERROR "Pinned LXMF receipt preparation failed")
endif()
execute_process(COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/prepare.py stamper
  ${LXMF_SOURCE}/src/LXMF/LXStamper.cpp ${CMAKE_CURRENT_BINARY_DIR}/PocketLXStamper.cpp RESULT_VARIABLE stamper_status)
if(NOT stamper_status EQUAL 0)
  message(FATAL_ERROR "Pinned cancellable stamp preparation failed")
endif()
add_library(pocket_rns SHARED engine.cpp
  ${CMAKE_CURRENT_BINARY_DIR}/PocketLXMRouter.cpp
  ${LXMF_SOURCE}/src/LXMF/LXMessage.cpp
  ${CMAKE_CURRENT_BINARY_DIR}/PocketLXStamper.cpp)
target_include_directories(pocket_rns PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/msgpack ${RNS_SOURCE}/src/microReticulum ${LXMF_SOURCE}/src ${LXMF_SOURCE}/src/LXMF)
target_link_libraries(pocket_rns PRIVATE microReticulum)
if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
  target_link_options(pocket_rns PRIVATE -static-libstdc++ -static-libgcc)
endif()
