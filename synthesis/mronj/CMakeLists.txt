cmake_minimum_required(VERSION 3.5)

include_directories(${CMAKE_CURRENT_SOURCE_DIR}/include)

# synthesis for mronj
add_executable(mronj
        src/main.cpp
        src/param.cpp
        src/synthesis.cpp
        src/debug.cpp
        )

target_link_libraries(mronj
        ${PanoramaCT_LIBRARIES}
        ${YAML_CPP_LIBRARIES}
        ${ITK_LIBRARIES}
        ${Boost_LIBRARIES}
        ${OpenCV_LIBRARIES}
        ${MPI_C_LIBRARIES}
        )