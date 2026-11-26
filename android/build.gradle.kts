allprojects {
    repositories {
        google()
        mavenCentral()
    }
}

val newBuildDir = rootProject.layout.projectDirectory.dir("../build")
rootProject.layout.buildDirectory.value(newBuildDir)

// Flutter gives Gradle the absolute output paths from its previous depfile.
// Discard relocated entries before Gradle prepares those output directories.
val flutterIntermediates = newBuildDir.dir("app/intermediates/flutter").asFile
val depfilePaths = Regex("""(\\ |\S)+""")
flutterIntermediates.listFiles()?.filter { it.isDirectory }?.forEach { variant ->
    val depfile = variant.resolve("flutter_build.d")
    if (depfile.isFile) {
        val outputPrefix = variant.absolutePath.replace(" ", "\\ ") + "/"
        val targets = depfile.bufferedReader().use { it.readLine().orEmpty().substringBefore(": ") }
        if (depfilePaths.findAll(targets).any { !it.value.startsWith(outputPrefix) }) {
            java.nio.file.Files.deleteIfExists(depfile.toPath())
            java.nio.file.Files.deleteIfExists(variant.resolve(".last_build_id").toPath())
        }
    }
}

subprojects {
    val newSubprojectBuildDir: Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)
}
subprojects {
    project.evaluationDependsOn(":app")
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
